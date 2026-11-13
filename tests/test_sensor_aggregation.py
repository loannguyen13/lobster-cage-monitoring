import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from backend.telemetry import InvalidTelemetry, encode as encode_cloud
from edge.aggregation import SensorAggregator
from edge.outbox import Outbox
from edge.sensor_telemetry import encode, decode, split_reading, UNITS
from edge.simulator import ROOT, read_payloads, main


class AggregationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readings = read_payloads(ROOT / 'lobster_cage_water_quality_synthetic.csv')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'queue.sqlite3'
        self.outbox = Outbox(self.path)
        self.agg = SensorAggregator(self.outbox, timeout_seconds=60)
        self.reading = deepcopy(self.readings[0])
        self.samples = list(split_reading(self.reading))

    def state(self):
        with self.outbox.connect() as db:
            return db.execute('SELECT state FROM sensor_groups').fetchone()[0]

    def test_reordered_restart_duplicate_reconstructs_exact_old_cloud_message(self):
        for s in self.samples[:3]:
            self.assertEqual(self.agg.accept(s, now=100), 'pending')
        self.assertIsNone(self.outbox.next())
        restarted = SensorAggregator(Outbox(self.path))
        self.assertEqual(restarted.accept(self.samples[0], now=102), 'duplicate')
        for s in reversed(self.samples[3:]):
            result = restarted.accept(s, now=103)
        self.assertEqual(result, 'queued')
        self.assertEqual(self.outbox.next(), (self.reading['message_id'], encode_cloud(self.reading)))
        self.outbox.mark_sent(self.reading['message_id'])
        for s in self.samples:
            self.assertEqual(restarted.accept(s, now=200), 'duplicate')
        self.assertIsNone(self.outbox.next())

    def test_missing_metric_expires_by_receipt_time_and_late_arrival_does_not_reopen(self):
        for s in self.samples:
            if s['metric'] != 'do': self.agg.accept(s, now=100)
        self.assertEqual(self.agg.expire(now=159), [])
        self.assertEqual(self.agg.expire(now=160), [(self.reading['device_id'],self.reading['timestamp'],['do'])])
        self.assertEqual(self.agg.expire(now=200), [])
        self.assertEqual(SensorAggregator(Outbox(self.path)).accept(self.samples[2], now=201),'expired')
        self.assertIsNone(self.outbox.next())

    def test_deadline_enforced_even_without_expiry_sweep(self):
        for s in self.samples[:-1]: self.agg.accept(s, now=0)
        self.assertEqual(self.agg.accept(self.samples[-1], now=60),'expired')
        self.assertIsNone(self.outbox.next())

    def test_device_and_event_time_never_mix(self):
        later = list(split_reading(self.readings[1]))
        other = deepcopy(self.reading); other['device_id'] = 'CAGE_B'
        other = list(split_reading(other))
        for s in self.samples[:3] + later[3:] + other[3:]: self.agg.accept(s, now=0)
        self.assertIsNone(self.outbox.next())
        for s in self.samples[3:]: self.agg.accept(s, now=1)
        self.assertEqual(self.outbox.next()[1], encode_cloud(self.reading))
        with self.outbox.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM messages').fetchone()[0],1)

    def test_conflicting_input_freezes_group(self):
        self.agg.accept(self.samples[0], now=0)
        changed = {**self.samples[0], 'value': 27.0}
        self.assertEqual(self.agg.accept(changed, now=1),'conflict')
        for s in self.samples[1:]: self.assertEqual(self.agg.accept(s, now=2),'conflict')
        self.assertIsNone(self.outbox.next())
        self.assertEqual(self.state(),'conflict')

    def test_new_id_for_same_metric_is_not_silently_overwritten(self):
        self.agg.accept(self.samples[0], now=0)
        self.assertEqual(self.agg.accept({**self.samples[0], 'message_id':str(uuid4())}, now=1),'conflict')
        self.assertEqual(self.state(),'conflict')

    def test_reused_id_across_groups_freezes_both(self):
        self.agg.accept(self.samples[0], now=0)
        changed = {**self.samples[0], 'device_id':'CAGE_B'}
        self.assertEqual(self.agg.accept(changed, now=1),'conflict')
        with self.outbox.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sensor_groups WHERE state='conflict'").fetchone()[0],2)

    def test_atomic_assembly_rolls_back_if_outbox_insert_fails(self):
        for s in self.samples[:-1]: self.agg.accept(s, now=0)
        with self.outbox.connect() as db:
            db.execute("CREATE TRIGGER fail_write BEFORE INSERT ON messages BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.agg.accept(self.samples[-1], now=1)
        with self.outbox.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sensor_samples').fetchone()[0],5)
            db.execute('DROP TRIGGER fail_write')
        self.assertEqual(self.state(),'pending')
        self.assertEqual(self.agg.accept(self.samples[-1], now=2),'queued')

    def test_concurrent_duplicates_queue_once(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda s:self.agg.accept(s,now=1),self.samples*2))
        self.assertEqual(results.count('queued'),1)
        self.assertEqual(self.outbox.next()[1],encode_cloud(self.reading))

    def test_existing_sent_outbox_and_budget_are_preserved(self):
        self.outbox.enqueue(self.reading['message_id'],encode_cloud(self.reading))
        self.outbox.mark_sent(self.reading['message_id'])
        self.assertTrue(self.outbox.reserve(encode_cloud(self.reading),2,'2026-11-13'))
        for s in self.samples: status=self.agg.accept(s,now=0)
        self.assertEqual(status,'duplicate')
        self.assertIsNone(self.outbox.next())
        self.assertFalse(self.outbox.reserve(encode_cloud(self.reading),2,'2026-11-13'))

    def test_conflict_with_legacy_cloud_outbox_preserves_original(self):
        self.outbox.enqueue(self.reading['message_id'],encode_cloud(self.reading))
        altered=deepcopy(self.samples); altered[0]['value']+=1
        for s in altered: status=self.agg.accept(s,now=0)
        self.assertEqual(status,'conflict')
        self.assertEqual(self.outbox.next()[1],encode_cloud(self.reading))

    def test_single_metric_contract_rejects_bad_values_units_shapes(self):
        sample=self.samples[2]
        for changes in [{'value':True},{'value':float('nan')},{'value':-1},
                        {'value':'4.65'},{'unit':'degC'},{'metric':[]},
                        {'timestamp':'2026-01-01'},{'schema_version':True},{'sensor_id':'extra'}]:
            with self.subTest(changes=changes), self.assertRaises(InvalidTelemetry):
                encode({**sample,**changes})
        for body in [b'{',b'{"a":1,"a":2}',b'x'*2049,b'\xff',encode_cloud(self.reading)]:
            with self.assertRaises(InvalidTelemetry):decode(body)
        for s in self.samples:
            self.assertEqual(decode(encode(s)),s)
            self.assertEqual(s['unit'],UNITS[s['metric']])
        self.assertEqual(list(split_reading(self.reading)),self.samples)

    def test_cli_publishes_six_independent_messages_and_missing_sensor_sends_five(self):
        for extra,expected in [([],6),(['--scenario','missing-data'],5),(['--sensor','do'],1)]:
            output=io.StringIO()
            with patch('sys.argv',['simulator','--dry-run','--limit','1',*extra]), \
                    patch('edge.simulator.make_client') as client, contextlib.redirect_stdout(output):
                main()
            client.assert_not_called()
            rows=[line for line in output.getvalue().splitlines() if ' payload=' in line]
            self.assertEqual(len(rows),expected)
            for row in rows:
                payload=json.loads(row.split(' payload=')[1])
                self.assertIn('/sensors/'+payload['metric'],row)
                self.assertNotIn('readings',payload)


if __name__=='__main__':unittest.main()
