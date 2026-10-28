import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

import jwt
import psycopg2
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.auth import principal
from backend.api.routes import database
from backend.api.schemas import time_range


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_and_auth_fail_closed(self):
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        with patch.dict(os.environ, {'AUTH_JWT_SECRET': ''}):
            self.assertEqual(self.client.get('/api/ponds').status_code, 503)
        with patch.dict(os.environ, {'AUTH_JWT_SECRET': 'test-only-secret-not-for-production-12345'}):
            self.assertEqual(self.client.get('/api/ponds').status_code, 401)

    def test_roles_bounds_and_database_errors(self):
        app.dependency_overrides[principal] = lambda: {'actor':'test-viewer', 'roles': {'Viewer'}}
        app.dependency_overrides[database] = lambda: None
        self.assertEqual(self.client.post('/api/alerts/1/acknowledge').status_code, 403)
        self.assertEqual(self.client.get('/api/audit-logs').status_code, 403)
        self.assertEqual(self.client.get('/api/readings?device_id=x&limit=1001').status_code, 422)
        with patch('backend.api.routes.rows', side_effect=psycopg2.OperationalError('SECRET-PASSWORD')):
            response = self.client.get('/api/ponds')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('SECRET', response.text)
            self.assertIn('X-Request-ID', response.headers)

    def test_time_range_requires_timezone_and_bounded_window(self):
        from fastapi import HTTPException
        now = datetime.now(timezone.utc)
        for start, end in [(now,now), (now-timedelta(days=8),now), (datetime.now(), now)]:
            with self.assertRaises(HTTPException):
                time_range(start, end)

    def test_signed_token_audience_expiration_and_roles(self):
        key = 'test-only-secret-not-for-production-12345'
        now = datetime.now(timezone.utc)
        claims = {'iss':'lobster-dashboard','aud':'lobster-dashboard-api',
                  'sub':'1','sid':str(uuid4()),'exp':now+timedelta(minutes=5),
                  'iat':now,'nbf':now}
        with patch.dict(os.environ, {'AUTH_JWT_SECRET':key}), \
             patch('backend.api.auth.session') as session:
            cur = session.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = {'id':1,'username':'operator','role':'Operator'}
            app.dependency_overrides[database] = lambda: None
            with patch('backend.api.routes.rows', return_value=[]):
                for change, status in [({},200), ({'aud':'wrong'},401),
                                       ({'exp':now-timedelta(seconds=1)},401), ({'sid':'invalid'},401)]:
                    token = jwt.encode(claims | change, key, algorithm='HS256')
                    response = self.client.get('/api/ponds', headers={'Authorization':f'Bearer {token}'})
                    self.assertEqual(response.status_code, status)
                cur.fetchone.return_value = None
                token = jwt.encode(claims,key,algorithm='HS256')
                self.assertEqual(self.client.get('/api/ponds',headers={'Authorization':f'Bearer {token}'}).status_code,401)

    def test_password_hash_and_signin_validation(self):
        from backend.services.accounts import hash_password, passwords
        hashed = hash_password('test-only-password-123')
        self.assertNotIn('test-only-password',hashed)
        self.assertTrue(passwords.verify('test-only-password-123',hashed))
        self.assertFalse(passwords.verify('incorrect',hashed))
        response = self.client.post('/api/auth/signin',json={'username':'demo','password':'x','role':'Admin'})
        self.assertEqual(response.status_code,422)

    def test_azure_entrypoint_indexes_both_triggers(self):
        from backend.function_app import app as azure_app
        functions = {f.get_function_name(): f.get_bindings_dict() for f in azure_app.get_functions()}
        self.assertIn('ingest', functions)
        self.assertIn('dashboard_api', functions)
        self.assertIn('eventHubTrigger', str(functions['ingest']))


if __name__ == '__main__':
    unittest.main()
