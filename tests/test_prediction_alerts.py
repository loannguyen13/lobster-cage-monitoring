import unittest
from datetime import datetime, timezone

from backend.services.prediction_alerts import evaluate_prediction


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None
        self.results = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        normalized = " ".join(query.split())
        self.connection.queries.append((normalized, params))
        if "FROM predictions p" in normalized:
            self.result = self.connection.prediction
            return
        if "FROM devices" in normalized:
            self.result = {"device_id": "device-1"}
            return
        if "FROM alert_rules" in normalized:
            self.results = [self.connection.rule]
            return
        if "FROM alerts" in normalized:
            self.result = next(
                (
                    alert
                    for alert in self.connection.alerts
                    if alert["rule_id"] == params[0]
                    and alert["device_id"] == params[1]
                    and alert["source_type"] == "predicted"
                    and alert["status"] == "open"
                ),
                None,
            )
            return
        if normalized.startswith("INSERT INTO alerts"):
            self.connection.next_alert_id += 1
            alert = {
                "id": self.connection.next_alert_id,
                "rule_id": params[0],
                "device_id": params[1],
                "pond_id": params[2],
                "source_type": "predicted",
                "severity": params[3],
                "status": "open",
                "first_prediction_id": params[4],
                "last_prediction_id": params[5],
                "opened_at": params[6],
                "last_observed_at": params[7],
                "first_value": params[8],
                "last_value": params[9],
                "worst_value": params[10],
                "rule_snapshot": params[11].adapted,
            }
            self.connection.alerts.append(alert)
            self.result = {"id": alert["id"]}
            return
        if normalized.startswith("UPDATE alerts"):
            (
                prediction_id,
                observed_at,
                value,
                worst_value,
                severity,
                status,
                resolved_at,
                alert_id,
            ) = params
            alert = next(
                alert
                for alert in self.connection.alerts
                if alert["id"] == alert_id
            )
            alert.update(
                last_prediction_id=prediction_id,
                last_observed_at=observed_at,
                last_value=value,
                worst_value=min(alert["worst_value"], worst_value),
                severity=severity,
                status=status,
                resolved_at=resolved_at,
            )
            self.result = None
            return
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.results


class FakeConnection:
    def __init__(self, predicted_do, *, model_used="xgboost"):
        observed_at = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        self.prediction = {
            "id": 100,
            "device_id": "device-1",
            "predicted_value": predicted_do,
            "generated_at": observed_at,
            "model_version": "xgboost-do-15m-v1",
            "model_used": model_used,
            "pond_id": 1,
        }
        self.rule = {
            "id": 7,
            "code": "low_do",
            "metric": "dissolved_oxygen",
            "version": 1,
            "warning_below": 4.0,
            "critical_below": 3.0,
            "recovery_above": 4.2,
        }
        self.alerts = []
        self.next_alert_id = 0
        self.queries = []

    def cursor(self, cursor_factory=None):
        return FakeCursor(self)


class PredictionAlertTests(unittest.TestCase):
    def test_warning_prediction_creates_predicted_alert(self):
        connection = FakeConnection(3.5)

        changed = evaluate_prediction(
            connection,
            prediction_id=100,
            model_used="xgboost",
        )

        self.assertEqual(changed, 1)
        self.assertEqual(len(connection.alerts), 1)
        alert = connection.alerts[0]
        self.assertEqual(alert["source_type"], "predicted")
        self.assertEqual(alert["severity"], "warning")
        self.assertEqual(alert["first_prediction_id"], 100)
        self.assertEqual(alert["status"], "open")

    def test_critical_prediction_creates_critical_alert(self):
        connection = FakeConnection(2.8)

        evaluate_prediction(connection, 100, model_used="xgboost")

        self.assertEqual(connection.alerts[0]["severity"], "critical")

    def test_open_episode_escalates_and_deescalates_then_resolves(self):
        connection = FakeConnection(3.5)
        evaluate_prediction(connection, 100, model_used="xgboost")
        alert_id = connection.alerts[0]["id"]

        connection.prediction.update(id=101, predicted_value=2.8)
        self.assertEqual(
            evaluate_prediction(connection, 101, model_used="xgboost"),
            1,
        )
        self.assertEqual(len(connection.alerts), 1)
        self.assertEqual(connection.alerts[0]["severity"], "critical")
        self.assertEqual(connection.alerts[0]["id"], alert_id)

        connection.prediction.update(id=102, predicted_value=3.5)
        evaluate_prediction(connection, 102, model_used="xgboost")
        self.assertEqual(connection.alerts[0]["severity"], "warning")

        connection.prediction.update(id=103, predicted_value=4.2)
        evaluate_prediction(connection, 103, model_used="xgboost")
        self.assertEqual(connection.alerts[0]["status"], "resolved")
        self.assertEqual(connection.alerts[0]["last_prediction_id"], 103)

    def test_reprocessing_an_open_prediction_does_not_duplicate_alert(self):
        connection = FakeConnection(3.5)
        evaluate_prediction(connection, 100, model_used="xgboost")

        evaluate_prediction(connection, 100, model_used="xgboost")

        self.assertEqual(len(connection.alerts), 1)
        self.assertEqual(connection.alerts[0]["first_prediction_id"], 100)

    def test_persistence_baseline_does_not_query_or_create_alerts(self):
        connection = FakeConnection(3.5, model_used="persistence")

        changed = evaluate_prediction(
            connection,
            prediction_id=100,
            model_used="persistence",
        )

        self.assertEqual(changed, 0)
        self.assertEqual(connection.queries, [])
        self.assertEqual(connection.alerts, [])

    def test_measured_episode_does_not_block_predicted_episode(self):
        connection = FakeConnection(3.5)
        connection.alerts.append(
            {
                "id": 88,
                "rule_id": 7,
                "device_id": "device-1",
                "source_type": "measured",
                "severity": "warning",
                "status": "open",
                "worst_value": 3.5,
            }
        )

        evaluate_prediction(connection, 100, model_used="xgboost")

        self.assertEqual(len(connection.alerts), 2)
        self.assertEqual(connection.alerts[0]["source_type"], "measured")
        self.assertEqual(connection.alerts[0]["status"], "open")
        self.assertEqual(connection.alerts[1]["source_type"], "predicted")
        alert_query = next(
            query
            for query, _ in connection.queries
            if "FROM alerts" in query
        )
        self.assertIn("source_type = 'predicted'", alert_query)


if __name__ == "__main__":
    unittest.main()
