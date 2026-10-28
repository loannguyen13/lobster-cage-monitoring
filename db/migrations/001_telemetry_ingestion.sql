-- Run after db/schemal.sql. Additive and rerunnable; existing rows are preserved.
BEGIN;
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    pond_id INT NOT NULL REFERENCES ponds(id),
    iothub_device_id TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true
);

ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS message_id UUID;
ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS device_id TEXT REFERENCES devices(device_id);
ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS turbidity REAL;
ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS chlorophyll_a REAL;
-- NULL for legacy records because their receipt time is unknown.
ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ;
ALTER TABLE sensor_readings ALTER COLUMN received_at SET DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS sensor_readings_message_id_key ON sensor_readings(message_id);
CREATE INDEX IF NOT EXISTS sensor_readings_device_time_idx ON sensor_readings(device_id, timestamp DESC);

-- Do not silently reassign a pre-existing pond or device.
INSERT INTO ponds(id,name) VALUES (1,'Van Phong - cage 01') ON CONFLICT (id) DO NOTHING;
INSERT INTO devices(device_id,pond_id,iothub_device_id)
VALUES ('LOBSTER_CAGE_VANPHONG_01',1,'pond-gateway-01')
ON CONFLICT (device_id) DO NOTHING;
COMMIT;
