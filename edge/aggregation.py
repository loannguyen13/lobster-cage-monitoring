"""Durable exact-event-time assembly, atomically handing complete rows to outbox."""
import json
import time

from backend.telemetry import FEATURES, encode as encode_cloud
from edge.sensor_telemetry import cloud_message_id, encode, validate


class SensorAggregator:
    def __init__(self, outbox, timeout_seconds=60):
        if not 1 <= timeout_seconds <= 86400:
            raise ValueError('Aggregation timeout must be 1..86400 seconds')
        self.outbox = outbox
        self.timeout = timeout_seconds
        with outbox.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sensor_groups (
                    device_id TEXT NOT NULL, measured_at TEXT NOT NULL,
                    deadline REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                    PRIMARY KEY(device_id,measured_at));
                CREATE INDEX IF NOT EXISTS sensor_groups_expiry
                    ON sensor_groups(state,deadline);
                CREATE TABLE IF NOT EXISTS sensor_samples (
                    message_id TEXT PRIMARY KEY, device_id TEXT NOT NULL,
                    measured_at TEXT NOT NULL, metric TEXT NOT NULL, body BLOB NOT NULL,
                    UNIQUE(device_id,measured_at,metric));
            ''')

    def accept(self, payload, now=None):
        """Commit before MQTT ACK; return pending/queued/duplicate/expired/conflict.

        Conflicts freeze pending groups. Completed outbox entries are immutable.
        Deadline uses local receipt time, not historic CSV measurement time.
        """
        payload = validate(payload)
        body = encode(payload)
        now = time.time() if now is None else now
        device, measured = payload['device_id'], payload['timestamp']
        key = (device, measured)
        with self.outbox.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT device_id,measured_at,body FROM sensor_samples WHERE message_id=?',
                                  (payload['message_id'],)).fetchone()
            if previous:
                if bytes(previous[2]) == body:
                    return 'duplicate'
                for affected in (key, (previous[0], previous[1])):
                    db.execute("INSERT OR IGNORE INTO sensor_groups(device_id,measured_at,deadline,state) VALUES (?,?,?,'conflict')", (*affected,now+self.timeout))
                    db.execute("UPDATE sensor_groups SET state='conflict' WHERE device_id=? AND measured_at=? AND state='pending'", affected)
                return 'conflict'
            db.execute('INSERT OR IGNORE INTO sensor_groups(device_id,measured_at,deadline) VALUES (?,?,?)',
                       (*key, now + self.timeout))
            state, deadline = db.execute('SELECT state,deadline FROM sensor_groups WHERE device_id=? AND measured_at=?',key).fetchone()
            if state == 'pending' and now >= deadline:
                db.execute("UPDATE sensor_groups SET state='expired' WHERE device_id=? AND measured_at=?",key)
                state = 'expired'
            if state in ('expired', 'conflict'):
                return state
            previous_metric = db.execute('SELECT body FROM sensor_samples WHERE device_id=? AND measured_at=? AND metric=?',
                                         (*key,payload['metric'])).fetchone()
            if previous_metric:
                # A second ID for a metric/time is ambiguous, even if values match.
                db.execute("UPDATE sensor_groups SET state='conflict' WHERE device_id=? AND measured_at=? AND state='pending'",key)
                return 'conflict'
            db.execute('INSERT INTO sensor_samples VALUES (?,?,?,?,?)',
                       (payload['message_id'],device,measured,payload['metric'],body))
            rows = db.execute('SELECT metric,body FROM sensor_samples WHERE device_id=? AND measured_at=?',key).fetchall()
            if len(rows) < len(FEATURES):
                return 'pending'
            values = {metric: json.loads(raw)['value'] for metric,raw in rows}
            message_id = cloud_message_id(device, measured)
            cloud_body = encode_cloud({'schema_version':1,'message_id':message_id,
                'device_id':device,'timestamp':measured,'readings':{m:values[m] for m in FEATURES}})
            existing = db.execute('SELECT body FROM messages WHERE message_id=?',(message_id,)).fetchone()
            if existing and bytes(existing[0]) != cloud_body:
                db.execute("UPDATE sensor_groups SET state='conflict' WHERE device_id=? AND measured_at=?",key)
                return 'conflict'
            db.execute('INSERT OR IGNORE INTO messages(message_id,body) VALUES (?,?)',(message_id,cloud_body))
            db.execute("UPDATE sensor_groups SET state='complete' WHERE device_id=? AND measured_at=?",key)
            return 'duplicate' if existing else 'queued'

    def expire(self, now=None):
        """Persist timeout decisions and report missing fields once per group."""
        now = time.time() if now is None else now
        with self.outbox.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            groups = db.execute("SELECT device_id,measured_at FROM sensor_groups WHERE state='pending' AND deadline<=?",(now,)).fetchall()
            result = []
            for device, measured in groups:
                present = {r[0] for r in db.execute('SELECT metric FROM sensor_samples WHERE device_id=? AND measured_at=?',(device,measured))}
                result.append((device,measured,[m for m in FEATURES if m not in present]))
            db.execute("UPDATE sensor_groups SET state='expired' WHERE state='pending' AND deadline<=?",(now,))
            return result
