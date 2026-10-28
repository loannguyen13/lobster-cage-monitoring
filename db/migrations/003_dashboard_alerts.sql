-- Run after 002, as database owner. Additive; does not rewrite legacy timestamps.
BEGIN;
ALTER TABLE ponds ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE ponds ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE devices ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS expected_interval_seconds INT NOT NULL DEFAULT 300 CHECK (expected_interval_seconds > 0);
ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_received_at TIMESTAMPTZ;
ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_measured_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS sensor_readings_pond_time_idx ON sensor_readings(pond_id,timestamp DESC,id DESC);
CREATE INDEX IF NOT EXISTS sensor_readings_latest_idx ON sensor_readings(device_id,timestamp DESC,id DESC) WHERE timestamp IS NOT NULL;

CREATE TABLE IF NOT EXISTS alert_rules (
    id BIGSERIAL PRIMARY KEY,
    pond_id INT NOT NULL REFERENCES ponds(id),
    code TEXT NOT NULL DEFAULT 'low_do',
    metric TEXT NOT NULL DEFAULT 'dissolved_oxygen' CHECK (metric='dissolved_oxygen'),
    warning_below REAL NOT NULL,
    critical_below REAL NOT NULL,
    recovery_above REAL NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    version INT NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pond_id,code),
    CHECK (critical_below >= 0 AND critical_below < warning_below AND warning_below < recovery_above AND recovery_above <= 30)
);
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT NOT NULL REFERENCES alert_rules(id),
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    pond_id INT NOT NULL REFERENCES ponds(id),
    severity TEXT NOT NULL CHECK (severity IN ('warning','critical')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
    first_reading_id INT NOT NULL REFERENCES sensor_readings(id),
    last_reading_id INT NOT NULL REFERENCES sensor_readings(id),
    opened_at TIMESTAMPTZ NOT NULL,
    last_observed_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    first_value REAL NOT NULL,
    last_value REAL NOT NULL,
    worst_value REAL NOT NULL,
    rule_snapshot JSONB NOT NULL,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT,
    CHECK ((status='open' AND resolved_at IS NULL) OR (status='resolved' AND resolved_at IS NOT NULL)),
    CHECK ((acknowledged_at IS NULL) = (acknowledged_by IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS alerts_one_open_idx ON alerts(rule_id,device_id) WHERE status='open';
CREATE INDEX IF NOT EXISTS alerts_pond_status_idx ON alerts(pond_id,status,id DESC);
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success','denied','failure')),
    request_id UUID NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
-- Experimental thresholds, NOT validated lobster husbandry limits.
INSERT INTO alert_rules(pond_id,warning_below,critical_below,recovery_above)
SELECT id,4,3,4.2 FROM ponds WHERE id=1 ON CONFLICT (pond_id,code) DO NOTHING;
-- Preserve measurements already ingested, without generating historical alerts.
UPDATE devices d SET
    last_received_at=COALESCE(d.last_received_at,s.received),
    last_measured_at=COALESCE(d.last_measured_at,s.measured)
FROM (SELECT device_id,max(received_at) received,max(timestamp) measured
      FROM sensor_readings GROUP BY device_id) s
WHERE d.device_id=s.device_id;
COMMIT;
