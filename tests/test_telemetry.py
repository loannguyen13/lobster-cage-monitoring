import json
import csv
import tempfile
import unittest
from pathlib import Path

from backend.telemetry import InvalidTelemetry, decode, encode, validate
from edge.gateway import accept_message
from edge.outbox import Outbox
from edge.simulator import ROOT, read_payloads


class TelemetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = read_payloads(ROOT / "lobster_cage_water_quality_synthetic.csv")

    def payload(self):
        return json.loads(json.dumps(self.payloads[0]))

    def test_actual_generated_dataset_contract(self):
        self.assertEqual(len(self.payloads), 2016)
        self.assertEqual(self.payloads[0]["timestamp"], "2026-09-30T17:00:00Z")
        self.assertEqual(self.payloads[0]["readings"]["do"], 4.65)
        self.assertEqual(len({p["message_id"] for p in self.payloads}), 2016)
        for payload in self.payloads:
            self.assertLess(len(encode(payload)), 512)
            self.assertEqual(decode(encode(payload)), payload)

    def test_replay_identity_is_stable(self):
        again = read_payloads(ROOT / "lobster_cage_water_quality_synthetic.csv")
        self.assertEqual(again[0]["message_id"], self.payloads[0]["message_id"])

    def test_multiple_devices_and_fractional_time_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.csv"
            columns = ["device_id", "timestamp", *self.payload()["readings"]]
            rows = [
                {"device_id": "CAGE_B", "timestamp": "2026-10-01T00:00:00.100+07:00", **self.payload()["readings"]},
                {"device_id": "CAGE_A", "timestamp": "2026-10-01T00:00:00+07:00", **self.payload()["readings"]},
            ]
            def write_rows(values):
                with path.open("w", newline="") as target:
                    writer = csv.DictWriter(target, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(values)
            write_rows(rows)
            self.assertEqual([p["device_id"] for p in read_payloads(path)], ["CAGE_A", "CAGE_B"])
            self.assertEqual(len(read_payloads(path, device="CAGE_B")), 1)
            write_rows(rows + [rows[1]])
            with self.assertRaises(ValueError):
                read_payloads(path)

    def test_missing_nan_bool_range_and_labels_rejected(self):
        for value in (float("nan"), float("inf"), True, -1, "4.65", 10 ** 1000):
            payload = self.payload()
            payload["readings"]["do"] = value
            with self.assertRaises(InvalidTelemetry):
                validate(payload)
        payload = self.payload()
        del payload["readings"]["do"]
        with self.assertRaises(InvalidTelemetry):
            validate(payload)
        payload = self.payload()
        payload["event_label"] = "normal"
        with self.assertRaises(InvalidTelemetry):
            validate(payload)

    def test_bad_json_duplicate_key_size_and_timestamp(self):
        for body in (b"{", b"x" * 2049, b'{"a":1,"a":2}', b"\xff"):
            with self.assertRaises(InvalidTelemetry):
                decode(body)
        payload = self.payload()
        payload["timestamp"] = "2026-10-01T00:00:00"
        with self.assertRaises(InvalidTelemetry):
            validate(payload)

    def test_topic_identity_and_allowlist(self):
        payload = self.payload()
        device = payload["device_id"]
        with self.assertRaises(InvalidTelemetry):
            accept_message("lobster/wrong/telemetry", encode(payload), {device})
        with self.assertRaises(InvalidTelemetry):
            accept_message(f"lobster/{device}/telemetry", encode(payload), {"other"})

    def test_outbox_restart_duplicate_conflict_and_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.db"
            first = Outbox(path)
            body = encode(self.payload())
            message_id = self.payload()["message_id"]
            first.enqueue(message_id, body)
            second = Outbox(path)
            second.enqueue(message_id, body)
            self.assertEqual(second.next(), (message_id, body))
            with self.assertRaises(ValueError):
                second.enqueue(message_id, b"different")
            self.assertTrue(second.reserve(body, 2, "2026-10-27"))
            self.assertFalse(first.reserve(body, 2, "2026-10-27"))
            self.assertTrue(first.reserve(body, 2, "2026-10-28"))
            first.mark_sent(message_id)
            self.assertIsNone(second.next())


if __name__ == "__main__":
    unittest.main()
