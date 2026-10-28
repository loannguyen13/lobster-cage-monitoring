import unittest
import json
from unittest.mock import patch

import azure.functions as func
from azure.functions.eventhub import EventHubTriggerConverter
from azure.functions.meta import Datum

from backend import ingestion
from backend.telemetry import encode, InvalidTelemetry
from edge.simulator import ROOT, read_payloads


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.payload = read_payloads(ROOT / "lobster_cage_water_quality_synthetic.csv")[0]
        self.handler = ingestion.ingest.build().get_user_function()

    def event(self, identity="pond-gateway-01", body=None):
        return func.EventHubEvent(body=body or encode(self.payload),
                                  iothub_metadata={"connection-device-id": identity} if identity else {})

    @patch.object(ingestion, "quarantine")
    @patch.object(ingestion, "connect")
    def test_missing_identity_never_touches_database(self, connect, quarantine):
        self.handler(self.event(identity=None))
        connect.assert_not_called()
        quarantine.assert_called_once()

    def test_sdk_extracts_identity_from_system_properties(self):
        event = EventHubTriggerConverter.decode(
            Datum(value=encode(self.payload), type="bytes"),
            trigger_metadata={"SystemProperties": Datum(
                value=json.dumps({"iothub-connection-device-id": "pond-gateway-01"}), type="json")},
        )
        self.assertEqual(event.iothub_metadata["connection-device-id"], "pond-gateway-01")

    @patch.object(ingestion, "quarantine")
    @patch.object(ingestion, "connect")
    def test_database_failure_escapes_for_retry(self, connect, quarantine):
        connect.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            self.handler(self.event())
        quarantine.assert_not_called()

    @patch.object(ingestion, "quarantine")
    @patch.object(ingestion, "save_reading")
    @patch.object(ingestion, "connect")
    def test_unauthorized_device_is_quarantined(self, connect, save, quarantine):
        save.side_effect = InvalidTelemetry("unauthorized")
        self.handler(self.event())
        quarantine.assert_called_once()
        connect.return_value.close.assert_called_once()

    @patch.object(ingestion, "quarantine")
    def test_quarantine_failure_escapes_for_retry(self, quarantine):
        quarantine.side_effect = RuntimeError("storage offline")
        with self.assertRaises(RuntimeError):
            self.handler(self.event(identity=None))

    @patch.object(ingestion, "save_reading", return_value=True)
    @patch.object(ingestion, "connect")
    def test_trusted_metadata_passed_to_repository(self, connect, save):
        self.handler(self.event())
        self.assertEqual(save.call_args.args[2], "pond-gateway-01")
        connect.return_value.__exit__.assert_called_once_with(None, None, None)
        connect.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
