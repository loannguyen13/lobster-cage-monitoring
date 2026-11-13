
"""Scheduled, in-process DO inference for Azure Functions."""
import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import xgboost as xgb

from backend.telemetry import BOUNDS, FEATURES


logger = logging.getLogger(__name__)

FORECAST_HORIZON_MINUTES = 15
FEATURE_SCHEMA_VERSION = 1
DEFAULT_MODEL_VERSION = "xgboost-do-15m-v1"
PERSISTENCE_MODEL_VERSION = "persistence-do-15m-v1"


def _get_model_version():
    model_version = os.getenv(
        "PREDICTION_MODEL_VERSION",
        DEFAULT_MODEL_VERSION,
    ).strip()
    if not model_version:
        raise ValueError("PREDICTION_MODEL_VERSION must not be empty.")
    return model_version


def _get_max_reading_age_minutes():
    raw_value = os.getenv(
        "PREDICTION_MAX_READING_AGE_MINUTES",
        str(FORECAST_HORIZON_MINUTES),
    )
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(
            "PREDICTION_MAX_READING_AGE_MINUTES must be a positive integer."
        ) from exc
    if value < 1:
        raise ValueError(
            "PREDICTION_MAX_READING_AGE_MINUTES must be a positive integer."
        )
    return value


def _model_artifact_paths():
    """Return packaged and repository-local model artifact locations."""
    backend_dir = Path(__file__).resolve().parents[1]
    repository_dir = backend_dir.parent
    return (
        backend_dir / "models",
        repository_dir / "experiments" / "results",
    )


def load_model():
    """Load and validate the 15-minute model and its feature schema."""
    model_dir = next(
        (
            directory
            for directory in _model_artifact_paths()
            if (directory / "selected_horizon_model.json").is_file()
        ),
        None,
    )

    if model_dir is None:
        raise FileNotFoundError(
            "Could not find selected_horizon_model.json in the Function "
            "artifact or experiments/results."
        )

    metadata_path = model_dir / "experiment_metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Missing model metadata: {metadata_path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("selected_horizon_minutes") != FORECAST_HORIZON_MINUTES:
        raise ValueError("Model metadata does not specify a 15-minute horizon.")
    if metadata.get("features") != list(FEATURES):
        raise ValueError("Model metadata feature order does not match telemetry.")

    booster = xgb.Booster()
    try:
        booster.load_model(str(model_dir / "selected_horizon_model.json"))
    except xgb.core.XGBoostError as exc:
        raise RuntimeError("Could not load the selected XGBoost model.") from exc

    if booster.num_features() != len(FEATURES):
        raise ValueError(
            f"Model expects {booster.num_features()} features; "
            f"{len(FEATURES)} are configured."
        )
    if booster.feature_names is not None and booster.feature_names != list(FEATURES):
        raise ValueError("Model feature order does not match telemetry.")

    return booster, _get_model_version()


def _predict_xgboost(model, reading):
    """Predict one future DO value using the shared six-feature order."""
    values = _build_feature_vector(reading)
    matrix = xgb.DMatrix([values], feature_names=list(FEATURES))
    result = float(model.predict(matrix)[0])
    if not math.isfinite(result):
        raise ValueError("XGBoost returned a non-finite DO prediction.")
    if not BOUNDS["do"][0] <= result <= BOUNDS["do"][1]:
        raise ValueError("XGBoost returned an out-of-range DO prediction.")
    return result


def _fetch_pending_readings(connection, limit):
    """Lock fresh, eligible readings that lack a prediction for this model."""
    model_version = _get_model_version()
    max_age_minutes = _get_max_reading_age_minutes()

    sql = """
        SELECT
            r.id,
            r.pond_id,
            r.device_id,
            r.timestamp,
            r.water_temperature,
            r.ph,
            r.dissolved_oxygen,
            r.salinity,
            r.turbidity,
            r.chlorophyll_a
        FROM sensor_readings r
        JOIN devices d
          ON d.device_id = r.device_id
         AND d.enabled = TRUE
        WHERE r.timestamp IS NOT NULL
          AND r.device_id IS NOT NULL
          AND r.pond_id IS NOT NULL
          AND r.water_temperature IS NOT NULL
          AND r.ph IS NOT NULL
          AND r.dissolved_oxygen IS NOT NULL
          AND r.salinity IS NOT NULL
          AND r.turbidity IS NOT NULL
          AND r.chlorophyll_a IS NOT NULL
          AND r.timestamp <= now()
          AND r.timestamp >= now() - (%s * INTERVAL '1 minute')
          AND NOT EXISTS (
              SELECT 1
              FROM predictions p
              WHERE p.source_reading_id = r.id
                AND p.model_version = %s
                AND p.horizon_minutes = %s
          )
        ORDER BY r.timestamp ASC, r.id ASC
        LIMIT %s
        FOR UPDATE OF r SKIP LOCKED
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            (
                max_age_minutes,
                model_version,
                FORECAST_HORIZON_MINUTES,
                limit,
            ),
        )
        rows = cursor.fetchall()

    readings = []

    for row in rows:
        readings.append({
            "reading_id": row[0],
            "pond_id": row[1],
            "device_id": row[2],
            "timestamp": row[3],
            "temperature": row[4],
            "ph": row[5],
            "do": row[6],
            "salinity": row[7],
            "turbidity": row[8],
            "chlorophyll_a": row[9],
        })

    return readings


def _build_feature_vector(reading):
    """Validate a reading and return its features in the trained model order."""
    timestamp = reading["timestamp"]

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(
            f"Reading {reading['reading_id']} has a naive timestamp."
        )

    values = []
    for feature in FEATURES:
        value = float(reading[feature])

        if not math.isfinite(value):
            raise ValueError(
                f"Reading {reading['reading_id']} has invalid {feature}."
            )

        lower, upper = BOUNDS[feature]

        if not lower <= value <= upper:
            raise ValueError(
                f"Reading {reading['reading_id']} has out-of-range {feature}."
            )

        values.append(value)

    return values


def _save_prediction(
    connection,
    reading,
    *,
    predicted_value,
    model_used,
    model_version,
    generated_at,
):
    """Persist prediction and provenance. Unique index prevents duplicates."""
    generated_at = generated_at.astimezone(timezone.utc)
    target_at = reading["timestamp"] + timedelta(
        minutes=FORECAST_HORIZON_MINUTES
    )
    target_at = target_at.astimezone(timezone.utc)

    # Legacy columns are TIMESTAMP WITHOUT TIME ZONE.
    # Store UTC-naive values there; new provenance columns use TIMESTAMPTZ.
    prediction_time_legacy = generated_at.replace(tzinfo=None)
    target_time_legacy = target_at.replace(tzinfo=None)

    sql = """
        INSERT INTO predictions (
            pond_id,
            model_used,
            parameter,
            predicted_value,
            prediction_time,
            target_time,
            source_reading_id,
            device_id,
            model_version,
            horizon_minutes,
            feature_schema_version,
            generated_at,
            target_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (
            source_reading_id,
            model_version,
            horizon_minutes
        )
        DO NOTHING
        RETURNING id
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            (
                reading["pond_id"],
                model_used,
                "dissolved_oxygen",
                predicted_value,
                prediction_time_legacy,
                target_time_legacy,
                reading["reading_id"],
                reading["device_id"],
                model_version,
                FORECAST_HORIZON_MINUTES,
                FEATURE_SCHEMA_VERSION,
                generated_at,
                target_at,
            ),
        )
        inserted = cursor.fetchone()

    return inserted[0] if inserted else None


def run_batch(connection, limit=50):
    """
    Predict pending sensor readings with Persistence and XGBoost.

    The caller owns the database transaction.
    Returns the number of newly inserted prediction records.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer.")

    model, model_version = load_model()
    readings = _fetch_pending_readings(connection, limit)

    inserted_count = 0
    generated_at = datetime.now(timezone.utc)

    for reading in readings:
        xgboost_value = _predict_xgboost(model, reading)
        predictions = (
            (
                "persistence",
                PERSISTENCE_MODEL_VERSION,
                float(reading["do"]),
            ),
            ("xgboost", model_version, xgboost_value),
        )

        if any(not math.isfinite(value) for _, _, value in predictions):
            raise ValueError("A model returned a non-finite DO prediction.")

        for model_used, version, predicted_value in predictions:
            prediction_id = _save_prediction(
                connection,
                reading,
                predicted_value=predicted_value,
                model_used=model_used,
                model_version=version,
                generated_at=generated_at,
            )
            if prediction_id is None:
                continue

            if model_used == "xgboost":
                from backend.services.prediction_alerts import evaluate_prediction

                evaluate_prediction(
                    connection,
                    prediction_id=prediction_id,
                    model_used="xgboost",
                )

            inserted_count += 1
            logger.info(
                "Prediction saved: id=%s model=%s version=%s "
                "device=%s reading=%s predicted_do=%.3f horizon=%s",
                prediction_id,
                model_used,
                version,
                reading["device_id"],
                reading["reading_id"],
                predicted_value,
                FORECAST_HORIZON_MINUTES,
            )

    logger.info(
        "Prediction batch finished: selected=%s inserted=%s",
        len(readings),
        inserted_count,
    )

    return inserted_count
