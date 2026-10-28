-- First create LOGIN role lobster_ingest and set its password privately.
-- Run as database owner in the target database, after the migration.
GRANT USAGE ON SCHEMA public TO lobster_ingest;
GRANT SELECT ON devices TO lobster_ingest;
GRANT SELECT, INSERT ON sensor_readings TO lobster_ingest;
GRANT USAGE, SELECT ON SEQUENCE sensor_readings_id_seq TO lobster_ingest;
-- Additional permissions after migration 003.
GRANT UPDATE (last_received_at,last_measured_at) ON devices TO lobster_ingest;
GRANT SELECT ON alert_rules TO lobster_ingest;
GRANT SELECT,INSERT,UPDATE ON alerts TO lobster_ingest;
GRANT USAGE ON SEQUENCE alerts_id_seq TO lobster_ingest;
-- Optional inference timer, after migration 004.
GRANT SELECT,INSERT ON predictions TO lobster_ingest;
GRANT USAGE ON SEQUENCE predictions_id_seq TO lobster_ingest;
