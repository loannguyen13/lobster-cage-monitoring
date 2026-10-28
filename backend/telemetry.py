"""Versioned wire contract shared by simulator, gateway and Azure ingestion."""

import json
import math
import re
from datetime import datetime, timezone
from uuid import UUID

FEATURES = ("temperature", "ph", "do", "salinity", "turbidity", "chlorophyll_a")
# Broad physical/sensor bounds, NOT biological alarm thresholds.
BOUNDS = {"temperature": (-5, 60), "ph": (0, 14), "do": (0, 30),
          "salinity": (0, 70), "turbidity": (0, 5000), "chlorophyll_a": (0, 10000)}
MAX_PAYLOAD_BYTES = 2048
DEVICE_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class InvalidTelemetry(ValueError):
    pass


def validate(payload):
    expected = {"schema_version", "message_id", "device_id", "timestamp", "readings"}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise InvalidTelemetry("Unexpected or missing envelope fields")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise InvalidTelemetry("Unsupported schema_version")
    if not isinstance(payload["device_id"], str) or not DEVICE_PATTERN.fullmatch(payload["device_id"]):
        raise InvalidTelemetry("Invalid device_id")
    try:
        if str(UUID(payload["message_id"])) != payload["message_id"]:
            raise ValueError()
        timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise InvalidTelemetry("Invalid UUID or timezone-aware timestamp") from None
    readings = payload["readings"]
    if not isinstance(readings, dict) or set(readings) != set(FEATURES):
        raise InvalidTelemetry("All six measurements are required")
    for name, value in readings.items():
        low, high = BOUNDS[name]
        if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
            raise InvalidTelemetry(f"Invalid measurement: {name}")
    normalized = dict(payload)
    normalized["timestamp"] = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return normalized


def encode(payload):
    body = json.dumps(validate(payload), separators=(",", ":"), allow_nan=False).encode()
    if len(body) > MAX_PAYLOAD_BYTES:
        raise InvalidTelemetry("Payload too large")
    return body


def decode(body):
    if len(body) > MAX_PAYLOAD_BYTES:
        raise InvalidTelemetry("Payload too large")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InvalidTelemetry("Duplicate JSON key")
            result[key] = value
        return result
    try:
        return validate(json.loads(body, object_pairs_hook=unique_pairs))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise InvalidTelemetry("Invalid JSON") from None
