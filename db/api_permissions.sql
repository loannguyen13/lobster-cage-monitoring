-- First create LOGIN role lobster_api and set its password privately.
-- Run as owner after 003. API cannot insert readings or edit mapping/rules.
GRANT USAGE ON SCHEMA public TO lobster_api;
GRANT SELECT ON ponds,devices,sensor_readings,alert_rules,alerts,audit_logs TO lobster_api;
GRANT UPDATE (acknowledged_at,acknowledged_by,updated_at) ON alerts TO lobster_api;
GRANT INSERT ON audit_logs TO lobster_api;
GRANT USAGE ON SEQUENCE audit_logs_id_seq TO lobster_api;
GRANT SELECT ON predictions TO lobster_api;
-- Run after 005. Account creation/password/role changes remain owner-only.
GRANT SELECT ON users,auth_sessions TO lobster_api;
GRANT UPDATE (failed_attempts,locked_until) ON users TO lobster_api;
GRANT INSERT ON auth_sessions TO lobster_api;
GRANT UPDATE (revoked_at) ON auth_sessions TO lobster_api;
