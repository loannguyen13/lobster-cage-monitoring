
-- Add support for prediction-based alert episodes.
-- Existing measured alerts remain unchanged.
BEGIN;

-- Existing alerts are measured alerts by default.
ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS source_type TEXT
    NOT NULL DEFAULT 'measured';

-- A predicted alert references prediction records instead of readings.
ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS first_prediction_id INT
    REFERENCES predictions(id);

ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS last_prediction_id INT
    REFERENCES predictions(id);

-- Reading references are nullable for prediction-based alerts.
ALTER TABLE alerts
    ALTER COLUMN first_reading_id DROP NOT NULL;

ALTER TABLE alerts
    ALTER COLUMN last_reading_id DROP NOT NULL;

-- Exactly one source type must be present.
ALTER TABLE alerts
    DROP CONSTRAINT IF EXISTS alerts_source_reference_check;

ALTER TABLE alerts
    ADD CONSTRAINT alerts_source_reference_check
    CHECK (
        (
            source_type = 'measured'
            AND first_reading_id IS NOT NULL
            AND last_reading_id IS NOT NULL
            AND first_prediction_id IS NULL
            AND last_prediction_id IS NULL
        )
        OR
        (
            source_type = 'predicted'
            AND first_reading_id IS NULL
            AND last_reading_id IS NULL
            AND first_prediction_id IS NOT NULL
            AND last_prediction_id IS NOT NULL
        )
    );

-- Allow one open measured episode and one open predicted episode
-- for the same device and alert rule.
DROP INDEX IF EXISTS alerts_one_open_idx;

CREATE UNIQUE INDEX IF NOT EXISTS alerts_one_open_per_source_idx
    ON alerts(rule_id, device_id, source_type)
    WHERE status = 'open';

CREATE INDEX IF NOT EXISTS alerts_first_prediction_idx
    ON alerts(first_prediction_id)
    WHERE first_prediction_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS alerts_last_prediction_idx
    ON alerts(last_prediction_id)
    WHERE last_prediction_id IS NOT NULL;

COMMIT;
