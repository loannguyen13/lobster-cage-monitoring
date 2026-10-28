"""Opt-in integration tests against a disposable LOCAL database only."""
import os
import unittest
from copy import deepcopy
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg2

from backend.repository import save_reading
from backend.telemetry import InvalidTelemetry
from edge.simulator import ROOT, read_payloads


@unittest.skipUnless(os.getenv("LOBSTER_TEST_POSTGRES") == "1", "requires disposable localhost:55432/ lobster_test")
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = psycopg2.connect(host="127.0.0.1", port=55432, dbname="lobster_test",
                                     user="postgres", password="test-only-local")
        with cls.admin, cls.admin.cursor() as cur:
            cur.execute((ROOT / "db/schemal.sql").read_text())
            cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name='sensor_readings' AND column_name='received_at'")
            if cur.fetchone():
                cur.execute("INSERT INTO sensor_readings(pond_id,dissolved_oxygen,received_at) VALUES (1,5,NULL) RETURNING id")
            else:
                cur.execute("INSERT INTO sensor_readings(pond_id,dissolved_oxygen) VALUES (1,5) RETURNING id")
            cls.legacy_id = cur.fetchone()[0]
        for _ in range(2):
            with cls.admin, cls.admin.cursor() as cur:
                cur.execute((ROOT / "db/migrations/001_telemetry_ingestion.sql").read_text())
                cur.execute((ROOT / "db/migrations/002_gateway_identity.sql").read_text())
                cur.execute((ROOT / "db/migrations/003_dashboard_alerts.sql").read_text())
                cur.execute((ROOT / "db/migrations/004_prediction_provenance.sql").read_text())
                cur.execute((ROOT / "db/migrations/005_local_auth.sql").read_text())
        with cls.admin, cls.admin.cursor() as cur:
            cur.execute("""DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='lobster_ingest') THEN
                    CREATE ROLE lobster_ingest LOGIN PASSWORD 'test-only-ingest';
                END IF;
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='lobster_api') THEN
                    CREATE ROLE lobster_api LOGIN PASSWORD 'test-only-api';
                END IF;
            END $$;""")
            cur.execute((ROOT / "db/ingestion_permissions.sql").read_text())
            cur.execute((ROOT / "db/api_permissions.sql").read_text())
        cls.writer = psycopg2.connect(host="127.0.0.1", port=55432, dbname="lobster_test",
                                      user="lobster_ingest", password="test-only-ingest")
        cls.base = read_payloads(ROOT / "lobster_cage_water_quality_synthetic.csv")[0]

    @classmethod
    def tearDownClass(cls):
        cls.writer.close()
        cls.admin.close()

    def payload(self):
        payload = deepcopy(self.base)
        payload["message_id"] = str(uuid4())
        return payload

    def test_migration_preserves_legacy_data(self):
        with self.admin, self.admin.cursor() as cur:
            cur.execute("SELECT dissolved_oxygen,received_at FROM sensor_readings WHERE id=%s", (self.legacy_id,))
            self.assertEqual(cur.fetchone(), (5.0, None))

    def test_mapping_columns_duplicate_and_conflict(self):
        payload = self.payload()
        with self.writer:
            self.assertTrue(save_reading(self.writer, payload, "pond-gateway-01"))
        with self.writer:
            self.assertFalse(save_reading(self.writer, payload, "pond-gateway-01"))
        with self.admin, self.admin.cursor() as cur:
            cur.execute("SELECT pond_id,water_temperature,dissolved_oxygen,turbidity,chlorophyll_a,received_at FROM sensor_readings WHERE message_id=%s", (payload["message_id"],))
            row = cur.fetchone()
            self.assertEqual(row[0], 1)
            for actual, expected in zip(row[1:5], (26.5, 4.65, 7.65, 7.22)):
                self.assertAlmostEqual(actual, expected, places=5)
            self.assertIsNotNone(row[5])
        payload["readings"]["do"] = 1.5
        with self.assertRaises(InvalidTelemetry), self.writer:
            save_reading(self.writer, payload, "pond-gateway-01")

    def test_unknown_and_spoofed_device_rejected(self):
        payload = self.payload()
        with self.assertRaises(InvalidTelemetry), self.writer:
            save_reading(self.writer, payload, "another-gateway")
        payload["device_id"] = "UNKNOWN"
        with self.assertRaises(InvalidTelemetry), self.writer:
            save_reading(self.writer, payload, "pond-gateway-01")

    def test_writer_cannot_change_device_mapping(self):
        with self.assertRaises(psycopg2.errors.InsufficientPrivilege), self.writer:
            with self.writer.cursor() as cur:
                cur.execute("UPDATE devices SET pond_id=2")

    def test_gateway_identity_upgrade_preserves_custom_mapping(self):
        migration = (ROOT / "db/migrations/002_gateway_identity.sql").read_text()
        device = "LOBSTER_CAGE_VANPHONG_01"
        try:
            with self.admin, self.admin.cursor() as cur:
                cur.execute("UPDATE devices SET iothub_device_id=%s WHERE device_id=%s",
                            ("lobster-gateway-01", device))
                cur.execute(migration)
                cur.execute(migration)
                cur.execute("SELECT iothub_device_id FROM devices WHERE device_id=%s", (device,))
                self.assertEqual(cur.fetchone()[0], "pond-gateway-01")
                cur.execute("UPDATE devices SET iothub_device_id=%s WHERE device_id=%s",
                            ("custom-gateway", device))
                cur.execute(migration)
                cur.execute("SELECT iothub_device_id FROM devices WHERE device_id=%s", (device,))
                self.assertEqual(cur.fetchone()[0], "custom-gateway")
        finally:
            with self.admin, self.admin.cursor() as cur:
                cur.execute("UPDATE devices SET iothub_device_id=%s WHERE device_id=%s",
                            ("pond-gateway-01", device))

    def new_device(self):
        device = 'TEST_' + uuid4().hex
        with self.admin, self.admin.cursor() as cur:
            cur.execute("INSERT INTO devices(device_id,pond_id,iothub_device_id) VALUES (%s,1,'pond-gateway-01')", (device,))
        return device

    def reading(self, device, minute, value):
        payload = self.payload()
        payload['device_id'] = device
        payload['timestamp'] = (datetime(2026,10,1,tzinfo=timezone.utc)+timedelta(minutes=minute)).isoformat()
        payload['readings']['do'] = value
        return payload

    def test_alert_lifecycle_ack_audit_and_late_reading(self):
        from fastapi.testclient import TestClient
        from backend.api.main import app
        from backend.api.auth import principal
        from backend.api.routes import database
        device = self.new_device()
        for minute, value in [(0,3.5),(5,2.5),(2,5.0)]:
            with self.writer:
                save_reading(self.writer, self.reading(device,minute,value), 'pond-gateway-01')
        with self.admin, self.admin.cursor() as cur:
            cur.execute('SELECT id,status,severity,worst_value FROM alerts WHERE device_id=%s', (device,))
            alert_id,status,level,worst = cur.fetchone()
            self.assertEqual((status,level,worst), ('open','critical',2.5))

        def api_db():
            conn = psycopg2.connect(host='127.0.0.1',port=55432,dbname='lobster_test',user='lobster_api',password='test-only-api')
            try:
                with conn:
                    yield conn
            finally:
                conn.close()
        app.dependency_overrides[database] = api_db
        app.dependency_overrides[principal] = lambda: {'actor':'operator-1','roles':{'Operator'}}
        try:
            client = TestClient(app)
            # Audit failure must not leave acknowledgment committed.
            with patch('backend.api.routes.acknowledged', side_effect=psycopg2.OperationalError('offline')):
                self.assertEqual(client.post(f'/api/alerts/{alert_id}/acknowledge').status_code,503)
            with self.admin, self.admin.cursor() as cur:
                cur.execute('SELECT acknowledged_at FROM alerts WHERE id=%s',(alert_id,))
                self.assertIsNone(cur.fetchone()[0])
            for _ in range(2):
                self.assertEqual(client.post(f'/api/alerts/{alert_id}/acknowledge').status_code,200)
            self.assertEqual(client.get(f'/api/alerts/{alert_id}').json()['status'],'open')
            query = {'device_id':device,'from':'2026-10-01T00:00:00Z','to':'2026-10-02T00:00:00Z','limit':2}
            page = client.get('/api/readings',params=query).json()
            self.assertEqual(len(page['items']),2)
            following = client.get('/api/readings',params=query | {'cursor':page['next_cursor']}).json()
            self.assertEqual(len(following['items']),1)
            self.assertEqual(client.get('/api/readings',params=query | {'device_id':"x' OR 1=1--"}).status_code,404)
        finally:
            app.dependency_overrides.clear()
        with self.writer:
            save_reading(self.writer,self.reading(device,10,4.3),'pond-gateway-01')
        with self.admin, self.admin.cursor() as cur:
            cur.execute('SELECT status FROM alerts WHERE id=%s',(alert_id,))
            self.assertEqual(cur.fetchone()[0],'resolved')
            cur.execute("SELECT count(*) FROM audit_logs WHERE resource_id=%s",(str(alert_id),))
            self.assertEqual(cur.fetchone()[0],1)

    def test_concurrent_delivery_and_alert_rollback(self):
        device = self.new_device()
        payload = self.reading(device,0,2.5)
        def send(_):
            conn = psycopg2.connect(host='127.0.0.1',port=55432,dbname='lobster_test',user='lobster_ingest',password='test-only-ingest')
            try:
                with conn:
                    return save_reading(conn,payload,'pond-gateway-01')
            finally:
                conn.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(send,range(4))),1)
        with self.admin, self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM alerts WHERE device_id=%s',(device,))
            self.assertEqual(cur.fetchone()[0],1)
        failed = self.reading(device,5,4.5)
        with patch('backend.services.readings.evaluate',side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError), self.writer:
                save_reading(self.writer,failed,'pond-gateway-01')
        with self.admin, self.admin.cursor() as cur:
            cur.execute('SELECT count(*) FROM sensor_readings WHERE message_id=%s',(failed['message_id'],))
            self.assertEqual(cur.fetchone()[0],0)

    def test_prediction_provenance_baseline_and_idempotency(self):
        from backend.services.predictions import run_batch
        device = self.new_device()
        payload = self.reading(device,0,5.5)
        with self.writer:
            save_reading(self.writer,payload,'pond-gateway-01')
        with self.writer:
            run_batch(self.writer,200)
        with self.writer:
            self.assertEqual(run_batch(self.writer,200),0)
        with self.admin, self.admin.cursor() as cur:
            cur.execute('''SELECT p.model_used,p.predicted_value,p.target_at-r.timestamp,p.model_version
                FROM predictions p JOIN sensor_readings r ON r.id=p.source_reading_id
                WHERE p.device_id=%s ORDER BY model_used''',(device,))
            results = cur.fetchall()
            self.assertEqual(len(results),2)
            self.assertEqual(results[0][0:2],('persistence',5.5))
            self.assertTrue(all(row[2]==timedelta(minutes=15) for row in results))
            self.assertTrue(results[1][3].startswith('xgboost-'))

    def test_local_auth_sessions_lockout_roles_and_reset(self):
        from contextlib import contextmanager
        from fastapi.testclient import TestClient
        from backend.api.main import app
        from backend.services.accounts import create_user,reset_password
        from backend.api.routes import database
        name = 'test_' + uuid4().hex
        password = 'test-only-account-password-123'
        with self.admin:
            user_id = create_user(self.admin,name,password,'Viewer')

        @contextmanager
        def api_session(**kwargs):
            conn = psycopg2.connect(host='127.0.0.1',port=55432,dbname='lobster_test',user='lobster_api',password='test-only-api')
            try:
                with conn:
                    yield conn
            finally:
                conn.close()
        def api_db():
            with api_session() as conn:
                yield conn
        app.dependency_overrides[database] = api_db
        try:
            with patch('backend.api.auth.session',api_session), patch.dict(os.environ,{'AUTH_JWT_SECRET':'test-only-secret-not-for-production-12345'}):
                client = TestClient(app)
                body = {'username':name,'password':password}
                for _ in range(5):
                    self.assertEqual(client.post('/api/auth/signin',json=body | {'password':'wrong'}).status_code,401)
                self.assertEqual(client.post('/api/auth/signin',json=body).status_code,401)
                with self.admin, self.admin.cursor() as cur:
                    cur.execute('SELECT failed_attempts FROM users WHERE id=%s',(user_id,))
                    self.assertEqual(cur.fetchone()[0],5)
                    cur.execute("UPDATE users SET locked_until=now()-interval '1 minute' WHERE id=%s",(user_id,))
                response = client.post('/api/auth/signin',json=body)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                token = response.json()['access_token']
                headers = {'Authorization':f'Bearer {token}'}
                self.assertEqual(client.get('/api/auth/me',headers=headers).json()['role'],'Viewer')
                self.assertEqual(client.post('/api/alerts/1/acknowledge',headers=headers).status_code,403)
                # Current DB role, not JWT claims, controls subsequent requests.
                with self.admin, self.admin.cursor() as cur:
                    cur.execute("UPDATE users SET role='Admin' WHERE id=%s",(user_id,))
                self.assertEqual(client.get('/api/audit-logs',headers=headers).status_code,200)
                self.assertEqual(client.post('/api/auth/logout',headers=headers).status_code,204)
                self.assertEqual(client.get('/api/auth/me',headers=headers).status_code,401)
                new_token = client.post('/api/auth/signin',json=body).json()['access_token']
                with self.admin:
                    reset_password(self.admin,name,'replacement-password-12345')
                self.assertEqual(client.get('/api/auth/me',headers={'Authorization':f'Bearer {new_token}'}).status_code,401)
                self.assertEqual(client.post('/api/auth/signin',json=body).status_code,401)
                with api_session() as conn:
                    with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                        with conn.cursor() as cur:
                            cur.execute("UPDATE users SET role='Admin' WHERE id=%s",(user_id,))
                        conn.rollback()
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
