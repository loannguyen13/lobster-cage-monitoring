"""Local JWT authentication with database-backed revocation and current roles."""
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from psycopg2.extras import RealDictCursor

from backend.database import session
from backend.services.accounts import passwords, dummy_hash, username

router = APIRouter(prefix='/api/auth', tags=['Authentication'])
bearer = HTTPBearer(auto_error=False)
ISSUER = 'lobster-dashboard'
AUDIENCE = 'lobster-dashboard-api'


def signing_key():
    key = os.getenv('AUTH_JWT_SECRET', '')
    if len(key.encode()) < 32 or key.startswith('<'):
        raise HTTPException(503, 'Authentication signing key is not configured')
    return key


def token_minutes():
    try:
        value = int(os.getenv('AUTH_TOKEN_MINUTES','60'))
        if not 5 <= value <= 120:
            raise ValueError()
        return value
    except ValueError:
        raise HTTPException(503, 'Authentication token duration is invalid') from None


class Signin(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3,max_length=64)
    password: str = Field(min_length=1,max_length=128,repr=False)

    @field_validator('username')
    @classmethod
    def normalize(cls, value):
        return username(value)


def unauthorized():
    return HTTPException(401,'Invalid credentials or inactive session',
                         headers={'WWW-Authenticate':'Bearer'})


def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    key = signing_key()
    if credentials is None:
        raise unauthorized()
    try:
        claims = jwt.decode(credentials.credentials,key,algorithms=['HS256'],
            issuer=ISSUER,audience=AUDIENCE,
            options={'require':['exp','iat','nbf','iss','aud','sub','sid']})
        sid = str(UUID(claims['sid']))
        user_id = int(claims['sub'])
        if user_id < 1:
            raise ValueError()
    except (jwt.PyJWTError,ValueError,TypeError,AttributeError):
        raise unauthorized() from None
    # Each request checks session revocation and the CURRENT role, not a stale JWT role.
    with session(api=True) as connection, connection.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('''SELECT u.id,u.username,u.role FROM auth_sessions s JOIN users u ON u.id=s.user_id
            WHERE s.id=%s AND s.user_id=%s AND s.revoked_at IS NULL AND s.expires_at>now() AND u.enabled''',
            (sid,user_id))
        user = cur.fetchone()
    if user is None:
        raise unauthorized()
    return {'actor':f"user:{user['id']}",'user_id':user['id'],'username':user['username'],
            'roles':{user['role']},'session_id':sid}


def operator(user=Depends(principal)):
    if not user['roles'].intersection({'Operator','Admin'}):
        raise HTTPException(403,'Operator role required')
    return user


def admin(user=Depends(principal)):
    if 'Admin' not in user['roles']:
        raise HTTPException(403,'Admin role required')
    return user


@router.post('/signin')
def signin(body: Signin, response: Response):
    key = signing_key()
    minutes = token_minutes()
    now = datetime.now(timezone.utc)
    sid = str(uuid4())
    expires = now + timedelta(minutes=minutes)
    token = None
    # Account row lock makes attempt counters consistent across Azure instances.
    with session(api=True) as connection, connection.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT * FROM users WHERE username=%s FOR UPDATE',(body.username,))
        user = cur.fetchone()
        locked = user and user['locked_until'] and user['locked_until'] > now
        if locked:
            # Stop expensive password hashing once an account is temporarily locked.
            pass
        else:
            valid = passwords.verify(body.password, user['password_hash'] if user else dummy_hash())
            if user and user['enabled'] and valid:
                cur.execute('UPDATE users SET failed_attempts=0,locked_until=NULL WHERE id=%s',(user['id'],))
                cur.execute('INSERT INTO auth_sessions(id,user_id,expires_at) VALUES (%s,%s,%s)',
                            (sid,user['id'],expires))
                token = jwt.encode({'sub':str(user['id']),'sid':sid,'iat':now,'nbf':now,
                                    'exp':expires,'iss':ISSUER,'aud':AUDIENCE},key,algorithm='HS256')
            elif user and user['enabled']:
                attempts = (0 if user['locked_until'] else user['failed_attempts']) + 1
                cur.execute('UPDATE users SET failed_attempts=%s,locked_until=%s WHERE id=%s',
                            (attempts,now+timedelta(minutes=15) if attempts>=5 else None,user['id']))
    # Raise AFTER committing failed attempts, not inside the transaction.
    if token is None:
        raise unauthorized()
    response.headers['Cache-Control'] = 'no-store'
    return {'access_token':token,'token_type':'bearer','expires_in':minutes*60}


@router.get('/me')
def me(response: Response, user=Depends(principal)):
    response.headers['Cache-Control'] = 'no-store'
    return {'id':user['user_id'],'username':user['username'],'role':next(iter(user['roles']))}


@router.post('/logout',status_code=204)
def logout(user=Depends(principal)):
    with session(api=True) as connection, connection.cursor() as cur:
        cur.execute('UPDATE auth_sessions SET revoked_at=now() WHERE id=%s AND user_id=%s AND revoked_at IS NULL',
                    (user['session_id'],user['user_id']))
    return Response(status_code=204,headers={'Cache-Control':'no-store'})
