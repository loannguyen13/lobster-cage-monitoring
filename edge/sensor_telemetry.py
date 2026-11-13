"""Local single-metric contract; cloud's six-feature contract remains unchanged."""
import json
from uuid import NAMESPACE_URL, uuid5

from backend.telemetry import FEATURES, MAX_PAYLOAD_BYTES, InvalidTelemetry, validate as validate_cloud

# Wire units; adapters must convert to these units, never silently relabel values.
UNITS = {'temperature': 'degC', 'ph': 'pH', 'do': 'mg/L', 'salinity': 'ppt',
         'turbidity': 'NTU', 'chlorophyll_a': 'ug/L'}


def cloud_message_id(device, timestamp):
    return str(uuid5(NAMESPACE_URL, f'lobster:v1:{device}:{timestamp}'))


def topic_for(payload):
    return f"lobster/{payload['device_id']}/sensors/{payload['metric']}"


def validate(payload):
    expected = {'schema_version', 'message_id', 'device_id', 'timestamp', 'metric', 'value', 'unit'}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise InvalidTelemetry('Unexpected or missing sensor fields')
    metric = payload['metric']
    if not isinstance(metric, str) or metric not in UNITS or payload['unit'] != UNITS[metric]:
        raise InvalidTelemetry('Unknown metric or incorrect unit')
    # Reuse identity/time/numeric rules without changing cloud validation.
    envelope = {key: payload[key] for key in ('schema_version', 'message_id', 'device_id', 'timestamp')}
    envelope['readings'] = {key: payload['value'] if key == metric else 0 for key in FEATURES}
    normalized = validate_cloud(envelope)
    return {'schema_version': payload['schema_version'], 'message_id': payload['message_id'],
            'device_id': payload['device_id'], 'timestamp': normalized['timestamp'],
            'metric': metric, 'value': payload['value'], 'unit': payload['unit']}


def encode(payload):
    body = json.dumps(validate(payload), separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(body) > MAX_PAYLOAD_BYTES:
        raise InvalidTelemetry('Sensor payload too large')
    return body


def decode(body):
    if len(body) > MAX_PAYLOAD_BYTES:
        raise InvalidTelemetry('Sensor payload too large')
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InvalidTelemetry('Duplicate JSON key')
            result[key] = value
        return result
    try:
        return validate(json.loads(body, object_pairs_hook=unique_pairs))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise InvalidTelemetry('Invalid sensor JSON') from None


def split_reading(reading):
    """One CSV observation becomes six independent MQTT publications."""
    reading = validate_cloud(reading)
    for metric in FEATURES:
        identity = f"lobster:sensor:v1:{reading['device_id']}:{reading['timestamp']}:{metric}"
        yield validate({
            'schema_version': 1, 'message_id': str(uuid5(NAMESPACE_URL, identity)),
            'device_id': reading['device_id'], 'timestamp': reading['timestamp'],
            'metric': metric, 'value': reading['readings'][metric], 'unit': UNITS[metric],
        })
