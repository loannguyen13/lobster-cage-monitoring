import math
import sys
import unittest
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import Mock, patch

from backend.services import predictions


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        self.connection.last_query = query
        self.connection.last_params = params
        if query.lstrip().startswith("SELECT"):
            self.rows = [self.connection.reading]
            return

        key = (params[6], params[8], params[9])
        if key in self.connection.saved:
            self.row = None
            return

        self.connection.saved.add(key)
        self.connection.inserts.append(params)
        self.connection.next_id += 1
        self.row = (self.connection.next_id,)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.reading = (
            12,
            1,
            "device-1",
            datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            26.5,
            7.8,
            5.5,
            35.0,
            7.2,
            4.1,
        )
        self.saved = set()
        self.inserts = []
        self.next_id = 0
        self.last_query = None
        self.last_params = None

    def cursor(self):
        return FakeCursor(self)


def reading_dict():
    return {
        "reading_id": 12,
        "pond_id": 1,
        "device_id": "device-1",
        "timestamp": datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
        "temperature": 26.5,
        "ph": 7.8,
        "do": 5.5,
        "salinity": 35.0,
        "turbidity": 7.2,
        "chlorophyll_a": 4.1,
    }


class PredictionServiceTests(unittest.TestCase):
    def test_batch_saves_persistence_and_xgboost_with_provenance(self):
        connection = FakeConnection()
        alert_service = ModuleType("backend.services.prediction_alerts")
        alert_service.evaluate_prediction = Mock()
        with (
            patch.dict(
                sys.modules,
                {"backend.services.prediction_alerts": alert_service},
            ),
            patch.object(
                predictions,
                "load_model",
                return_value=(object(), "xgboost-do-15m-v1"),
            ),
            patch.object(predictions, "_predict_xgboost", return_value=4.75),
        ):
            count = predictions.run_batch(connection)

        self.assertEqual(count, 2)
        alert_service.evaluate_prediction.assert_called_once_with(
            connection,
            prediction_id=2,
            model_used="xgboost",
        )
        self.assertEqual(
            connection.saved,
            {
                (12, predictions.PERSISTENCE_MODEL_VERSION, 15),
                (12, "xgboost-do-15m-v1", 15),
            },
        )
        self.assertEqual(
            [row[1:4] for row in connection.inserts],
            [
                ("persistence", "dissolved_oxygen", 5.5),
                ("xgboost", "dissolved_oxygen", 4.75),
            ],
        )
        expected_target = connection.reading[3] + predictions.timedelta(
            minutes=predictions.FORECAST_HORIZON_MINUTES
        )
        self.assertTrue(
            all(row[12] == expected_target for row in connection.inserts)
        )

        with (
            patch.object(
                predictions,
                "load_model",
                return_value=(object(), "xgboost-do-15m-v1"),
            ),
            patch.object(predictions, "_predict_xgboost", return_value=4.75),
            patch.dict(
                sys.modules,
                {"backend.services.prediction_alerts": alert_service},
            ),
        ):
            self.assertEqual(predictions.run_batch(connection), 0)
        alert_service.evaluate_prediction.assert_called_once()

    def test_feature_mapping_rejects_nonfinite_and_out_of_range_values(self):
        reading = reading_dict()
        values = predictions._build_feature_vector(reading)
        self.assertEqual(
            values,
            [26.5, 7.8, 5.5, 35.0, 7.2, 4.1],
        )

        reading["do"] = math.nan
        with self.assertRaisesRegex(ValueError, "invalid do"):
            predictions._build_feature_vector(reading)

        reading["do"] = 31
        with self.assertRaisesRegex(ValueError, "out-of-range do"):
            predictions._build_feature_vector(reading)

    def test_load_model_uses_repository_artifact_and_predicts_finite_value(self):
        with patch.dict(
            "os.environ",
            {"PREDICTION_MODEL_VERSION": predictions.DEFAULT_MODEL_VERSION},
        ):
            model, version = predictions.load_model()
            value = predictions._predict_xgboost(model, reading_dict())

        self.assertEqual(version, predictions.DEFAULT_MODEL_VERSION)
        self.assertTrue(math.isfinite(value))

    def test_nonfinite_model_output_is_not_saved(self):
        connection = FakeConnection()
        with (
            patch.object(
                predictions,
                "load_model",
                return_value=(object(), "xgboost-do-15m-v1"),
            ),
            patch.object(predictions, "_predict_xgboost", return_value=math.nan),
            self.assertRaisesRegex(ValueError, "non-finite DO prediction"),
        ):
            predictions.run_batch(connection)

        self.assertEqual(connection.saved, set())

    def test_batch_limit_must_be_positive_integer(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            predictions.run_batch(FakeConnection(), limit=0)

        with self.assertRaisesRegex(ValueError, "positive integer"):
            predictions.run_batch(FakeConnection(), limit=True)

    def test_pending_query_excludes_future_and_stale_readings(self):
        connection = FakeConnection()
        predictions._fetch_pending_readings(connection, limit=7)

        self.assertIn("r.timestamp <= now()", connection.last_query)
        self.assertIn(
            "r.timestamp >= now() - (%s * INTERVAL '1 minute')",
            connection.last_query,
        )
        self.assertEqual(
            connection.last_params,
            (15, predictions.DEFAULT_MODEL_VERSION, 15, 7),
        )

        with patch.dict(
            "os.environ",
            {"PREDICTION_MAX_READING_AGE_MINUTES": "0"},
        ):
            with self.assertRaisesRegex(ValueError, "positive integer"):
                predictions._fetch_pending_readings(connection, limit=7)


if __name__ == "__main__":
    unittest.main()
