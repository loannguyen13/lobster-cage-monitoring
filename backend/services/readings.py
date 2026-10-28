import math
from datetime import datetime
from backend.telemetry import FEATURES, InvalidTelemetry
from backend.services.alerts import evaluate


def save_reading(connection, payload, authenticated_gateway):
    """Caller owns transaction. Mapping is authoritative; payload has no pond_id."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT pond_id,last_measured_at FROM devices
            WHERE device_id=%s AND iothub_device_id=%s AND enabled=true FOR UPDATE
        """, (payload["device_id"], authenticated_gateway))
        row = cursor.fetchone()
        if row is None:
            raise InvalidTelemetry("Unknown, disabled, or unauthorized device")
        readings = payload["readings"]
        cursor.execute("""
            INSERT INTO sensor_readings
                (message_id, device_id, pond_id, timestamp, water_temperature,
                 ph, dissolved_oxygen, salinity, turbidity, chlorophyll_a)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (message_id) DO NOTHING
            RETURNING id
        """, (payload["message_id"], payload["device_id"], row[0], payload["timestamp"],
              *(readings[key] for key in FEATURES)))
        inserted = cursor.fetchone()
        if inserted:
            measured_at = datetime.fromisoformat(payload['timestamp'].replace('Z', '+00:00'))
            cursor.execute('UPDATE devices SET last_received_at=now(), last_measured_at=GREATEST(last_measured_at,%s) WHERE device_id=%s', (measured_at, payload['device_id']))
            if row[1] is None or measured_at > row[1]:
                evaluate(connection, payload['device_id'], row[0], inserted[0], measured_at, readings['do'])
            return True
        # Duplicate IDs with different contents are not silently accepted.
        cursor.execute("""
            SELECT device_id, timestamp, water_temperature, ph, dissolved_oxygen,
                   salinity, turbidity, chlorophyll_a
            FROM sensor_readings WHERE message_id=%s
        """, (payload["message_id"],))
        stored = cursor.fetchone()
        measured_at = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
        matches = stored and stored[0] == payload["device_id"] and stored[1] == measured_at
        matches = matches and all(math.isclose(float(a), readings[key], rel_tol=1e-6, abs_tol=1e-6)
                                  for a, key in zip(stored[2:], FEATURES))
        if not matches:
            raise InvalidTelemetry("message_id reused with different content")
        return False
