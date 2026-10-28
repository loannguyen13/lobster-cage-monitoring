"""Password hashing and owner-only account management shared with the CLI."""
import re
from functools import lru_cache
import secrets

from pwdlib import PasswordHash

passwords = PasswordHash.recommended()


def username(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[a-z0-9_.-]{3,64}', value):
        raise ValueError('Username must be 3..64 lowercase letters, digits, _, . or -')
    return value


def hash_password(value):
    if not 6 <= len(value) <= 128:
        raise ValueError('Password must contain 6..128 characters')
    return passwords.hash(value)


@lru_cache(maxsize=1)
def dummy_hash():
    return passwords.hash(secrets.token_urlsafe(32))


def create_user(connection, name, password, role):
    name = username(name)
    if role not in ('Viewer','Operator','Admin'):
        raise ValueError('Unknown role')
    hashed = hash_password(password)
    with connection.cursor() as cur:
        cur.execute('INSERT INTO users(username,password_hash,role) VALUES (%s,%s,%s) RETURNING id',
                    (name,hashed,role))
        return cur.fetchone()[0]


def reset_password(connection, name, password):
    hashed = hash_password(password)
    with connection.cursor() as cur:
        cur.execute('''UPDATE users SET password_hash=%s,failed_attempts=0,locked_until=NULL,
            updated_at=now() WHERE username=%s RETURNING id''', (hashed,username(name)))
        row = cur.fetchone()
        if row is None:
            raise ValueError('Account not found')
        cur.execute('UPDATE auth_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL', (row[0],))
