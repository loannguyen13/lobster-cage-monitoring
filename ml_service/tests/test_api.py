
from datetime import datetime, timedelta
from math import isfinite

import pytest

from fastapi.testclient import TestClient

from ml_service.app.main import app


@pytest.fixture(scope="module")
def client():
    """
    Start FastAPI application and execute lifespan.
    """

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_payload():
    return {
        "device_id": "LOBSTER_CAGE_VANPHONG_01",
        "timestamp": "2026-10-01T00:00:00+07:00",
        "temperature": 29.5,
        "ph": 8.1,
        "do": 4.65,
        "salinity": 32.0,
        "turbidity": 15.2,
        "chlorophyll_a": 2.3
    }


def test_health_check(client):

    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"
    assert data["model_loaded"] is True


def test_model_info(client):

    response = client.get("/model/info")

    assert response.status_code == 200

    data = response.json()

    assert data["forecast_horizon_minutes"] == 15
    assert data["forecast_target"] == "do_future_15m"

    assert data["boosting_rounds"] == 200

    assert data["features"] == [
        "temperature",
        "ph",
        "do",
        "salinity",
        "turbidity",
        "chlorophyll_a"
    ]


def test_predict_success(client, valid_payload):

    response = client.post(
        "/predict",
        json=valid_payload
    )

    assert response.status_code == 200

    data = response.json()

    assert data["device_id"] == valid_payload["device_id"]

    assert data["prediction_horizon_minutes"] == 15

    assert isfinite(data["predicted_do"])

    assert data["current_do"] == valid_payload["do"]

    assert data["unit"] == "mg/L"


def test_forecast_timestamp(client, valid_payload):

    response = client.post(
        "/predict",
        json=valid_payload
    )

    assert response.status_code == 200

    data = response.json()

    source_time = datetime.fromisoformat(
        data["source_timestamp"]
    )

    forecast_time = datetime.fromisoformat(
        data["forecast_timestamp"]
    )

    expected_time = source_time + timedelta(minutes=15)

    assert forecast_time == expected_time


def test_missing_feature_rejected(client, valid_payload):

    invalid_payload = valid_payload.copy()

    invalid_payload.pop("temperature")

    response = client.post(
        "/predict",
        json=invalid_payload
    )

    assert response.status_code == 422


def test_future_target_rejected(client, valid_payload):

    invalid_payload = valid_payload.copy()

    invalid_payload["do_future_15m"] = 4.0

    response = client.post(
        "/predict",
        json=invalid_payload
    )

    assert response.status_code == 422


def test_timestamp_without_timezone_rejected(
    client,
    valid_payload
):

    invalid_payload = valid_payload.copy()

    invalid_payload["timestamp"] = "2026-10-01T00:00:00"

    response = client.post(
        "/predict",
        json=invalid_payload
    )

    assert response.status_code == 422
