# API Reference — Dashboard Backend


## 1. Base URL, Swagger, and Authentication

- Local: `http://localhost:9000`.
- Cloud: the actual App Service HTTPS URL, without :9000.
- Swagger: `/api/docs`; OpenAPI JSON: `/api/openapi.json`.
- Requests and responses use JSON, except successful logout returns 204 with no body.
- Data endpoints require `Authorization: Bearer <access_token>`; signin and health are public.

## 2. Endpoint Catalog

`V/O/A` means Viewer, Operator, or Admin. Required query parameters have no default.

| Method and path | Permission | Main input | Purpose |
|---|---|---|---|
| GET /api/health | Public | None | Check the HTTP application, not the database, IoT flow, or model |
| POST /api/auth/signin | Public | JSON username, password | Obtain a JWT and create a session |
| GET /api/auth/me | Authenticated | Bearer token | Retrieve id, username, and role |
| POST /api/auth/logout | Authenticated | Bearer token, no body | Revoke the current session |
| GET /api/ponds | V/O/A | None | List cages with names, status, and metadata |
| GET /api/devices | V/O/A | Required pond_id >0 | List cage devices and latest measurement/receipt times |
| GET /api/readings/latest | V/O/A | Required pond_id >0 | Get one latest reading per device in the cage |
| GET /api/readings | V/O/A | Required device_id; from, to, limit, cursor | Retrieve sensor history for charts |
| GET /api/dashboard | V/O/A | Required pond_id >0 | Get latest readings and open-alert counts by severity |
| GET /api/alert-rules | V/O/A | Required pond_id >0 | View thresholds and rule versions |
| GET /api/alerts | V/O/A | Required pond_id >0; status, limit, cursor | List alert episodes |
| GET /api/alerts/{alert_id} | V/O/A | Path ID | Get alert details and the rule snapshot |
| POST /api/alerts/{alert_id}/acknowledge | O/A | Path ID, no body | Record that an operator has seen the alert |
| GET /api/audit-logs | Admin | limit, cursor | Retrieve recorded audit events |
| GET /api/predictions/latest | V/O/A | Required device_id | Get the latest prediction per model_used |
| GET /api/predictions | V/O/A | Required device_id; from, to, limit, cursor | Retrieve prediction history filtered by target_at |
