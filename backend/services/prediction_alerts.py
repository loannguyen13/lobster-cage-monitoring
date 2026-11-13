
"""Predicted DO alert episodes.

Only XGBoost predictions should be passed to this service.
The caller owns the database transaction.
"""

from psycopg2.extras import RealDictCursor, Json


def severity(value, rule):
    """Return the alert severity for a predicted DO value."""
    if value < rule["critical_below"]:
        return "critical"

    if value < rule["warning_below"]:
        return "warning"

    return None


def evaluate_prediction(connection, prediction_id, *, model_used):
    """Create, update, or resolve predicted alert episodes.

    Args:
        connection: Existing PostgreSQL connection.
        prediction_id: ID returned when the prediction was saved.
        model_used: Model identifier, expected to be 'xgboost'.

    Returns:
        Number of alert episodes changed.
    """
    # Persistence is a baseline, not a production alert source.
    if model_used != "xgboost":
        return 0

    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        # Load the saved prediction and its device/pond information.
        cur.execute(
            """
            SELECT
                p.id,
                p.device_id,
                p.predicted_value,
                p.generated_at,
                p.model_version,
                d.pond_id
            FROM predictions p
            JOIN devices d ON d.device_id = p.device_id
            WHERE p.id = %s
            """,
            (prediction_id,),
        )
        prediction = cur.fetchone()

        if prediction is None:
            raise ValueError(
                f"Prediction {prediction_id} does not exist "
                "or has no associated device."
            )

        if prediction["generated_at"] is None:
            raise ValueError(
                f"Prediction {prediction_id} has no generated_at timestamp."
            )

        device = prediction["device_id"]
        pond = prediction["pond_id"]
        value = float(prediction["predicted_value"])
        observed_at = prediction["generated_at"]

        # Serialize alert evaluation for the same device.
        # This follows the device-row locking approach used by ingestion.
        cur.execute(
            """
            SELECT device_id
            FROM devices
            WHERE device_id = %s
            FOR UPDATE
            """,
            (device,),
        )

        if cur.fetchone() is None:
            raise ValueError(f"Device {device} does not exist.")

        cur.execute(
            """
            SELECT *
            FROM alert_rules
            WHERE pond_id = %s
              AND enabled = TRUE
            ORDER BY id
            """,
            (pond,),
        )
        rules = cur.fetchall()

        changed = 0

        for rule in rules:
            cur.execute(
                """
                SELECT *
                FROM alerts
                WHERE rule_id = %s
                  AND device_id = %s
                  AND source_type = 'predicted'
                  AND status = 'open'
                FOR UPDATE
                """,
                (rule["id"], device),
            )
            active = cur.fetchone()

            # An open episode retains the rule configuration
            # that was active when that episode started.
            thresholds = active["rule_snapshot"] if active else rule
            level = severity(value, thresholds)

            if active:
                resolved = value >= thresholds["recovery_above"]

                cur.execute(
                    """
                    UPDATE alerts
                    SET
                        last_prediction_id = %s,
                        last_observed_at = %s,
                        last_value = %s,
                        worst_value = LEAST(worst_value, %s),
                        severity = %s,
                        status = %s,
                        resolved_at = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        prediction_id,
                        observed_at,
                        value,
                        value,
                        level or active["severity"],
                        "resolved" if resolved else "open",
                        observed_at if resolved else None,
                        active["id"],
                    ),
                )
                changed += 1

            elif level:
                snapshot = {
                    key: rule[key]
                    for key in (
                        "code",
                        "metric",
                        "version",
                        "warning_below",
                        "critical_below",
                        "recovery_above",
                    )
                }

                cur.execute(
                    """
                    INSERT INTO alerts (
                        rule_id,
                        device_id,
                        pond_id,
                        source_type,
                        severity,
                        status,
                        first_prediction_id,
                        last_prediction_id,
                        opened_at,
                        last_observed_at,
                        first_value,
                        last_value,
                        worst_value,
                        rule_snapshot
                    )
                    VALUES (
                        %s, %s, %s, 'predicted', %s, 'open',
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        rule["id"],
                        device,
                        pond,
                        level,
                        prediction_id,
                        prediction_id,
                        observed_at,
                        observed_at,
                        value,
                        value,
                        value,
                        Json(snapshot),
                    ),
                )
                cur.fetchone()
                changed += 1

        return changed
