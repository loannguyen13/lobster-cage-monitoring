-- Preserve legacy naive timestamps: use explicitly named UTC-aware columns for new predictions.
BEGIN;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS source_reading_id INT REFERENCES sensor_readings(id);
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS device_id TEXT REFERENCES devices(device_id);
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS model_version TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS horizon_minutes INT CHECK (horizon_minutes > 0);
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS feature_schema_version INT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS target_at TIMESTAMPTZ;
ALTER TABLE predictions ALTER COLUMN predicted_value TYPE DOUBLE PRECISION;
CREATE UNIQUE INDEX IF NOT EXISTS predictions_source_model_idx ON predictions(source_reading_id,model_version,horizon_minutes);
CREATE INDEX IF NOT EXISTS predictions_device_target_idx ON predictions(device_id,target_at DESC,id DESC);
COMMIT;
