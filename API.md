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

## 3. Frontend Contract — Predictions and Alerts

These are read endpoints. The scheduled backend job creates prediction and alert
records; the frontend must not create them. All timestamps are ISO-8601 strings
with a timezone (normally `Z`). Values below are representative synthetic mock
data, not live farm measurements or validated aquaculture thresholds.

### 3.1 Sign in and authenticated requests

Sign in to obtain the bearer token:

```http
POST /api/auth/signin
Content-Type: application/json

{"username":"viewer","password":"<password>"}
```

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Send `Authorization: Bearer <access_token>` on data requests. Sign-in failures
return `401`; missing auth configuration may return `503`.

### 3.2 Latest predictions for a device

```http
GET /api/predictions/latest?device_id=LOBSTER_CAGE_VANPHONG_01
Authorization: Bearer <access_token>
```

```json
{
  "items": [
    {
      "id": 812,
      "source_reading_id": 1204,
      "device_id": "LOBSTER_CAGE_VANPHONG_01",
      "model_used": "xgboost",
      "model_version": "xgboost-do-15m-v1",
      "horizon_minutes": 15,
      "predicted_value": 3.72,
      "generated_at": "2026-11-14T00:10:00Z",
      "target_at": "2026-11-14T00:25:00Z"
    },
    {
      "id": 811,
      "source_reading_id": 1204,
      "device_id": "LOBSTER_CAGE_VANPHONG_01",
      "model_used": "persistence",
      "model_version": "persistence-do-15m-v1",
      "horizon_minutes": 15,
      "predicted_value": 3.9,
      "generated_at": "2026-11-14T00:10:00Z",
      "target_at": "2026-11-14T00:25:00Z"
    }
  ],
  "data_source": "synthetic_replay"
}
```

This returns at most one latest row per `model_used`, so the list can include
both `xgboost` and `persistence`. Treat `predicted_value` as predicted DO in
mg/L. An empty `items` array means the device has no prediction records yet.
The response does not include the source reading's current DO; request
`/api/readings/latest?pond_id=<pond_id>` separately if the screen needs it.

### 3.3 Prediction history

```http
GET /api/predictions?device_id=LOBSTER_CAGE_VANPHONG_01&from=2026-11-13T00:00:00Z&to=2026-11-14T00:00:00Z&limit=100
Authorization: Bearer <access_token>
```

The time range filters `target_at` using an inclusive `from` and exclusive
`to`. Both values must include a timezone. If omitted, the API uses the last 24
hours. A range must be positive and no longer than seven days. `limit` defaults
to 100 and must be from 1 through 1000.

```json
{
  "items": [
    {
      "id": 812,
      "source_reading_id": 1204,
      "device_id": "LOBSTER_CAGE_VANPHONG_01",
      "model_used": "xgboost",
      "model_version": "xgboost-do-15m-v1",
      "horizon_minutes": 15,
      "predicted_value": 3.72,
      "generated_at": "2026-11-14T00:10:00Z",
      "target_at": "2026-11-14T00:25:00Z"
    }
  ],
  "next_cursor": 812
}
```

Pass the returned cursor unchanged to fetch the next page:

```http
GET /api/predictions?device_id=LOBSTER_CAGE_VANPHONG_01&from=2026-11-13T00:00:00Z&to=2026-11-14T00:00:00Z&limit=100&cursor=812
```

`next_cursor` is the last returned prediction ID, or `null` when there is no
next page. History pages are ordered by descending ID. `404` means the device
does not exist; invalid time ranges or malformed/non-positive cursors return
`422`.

### 3.4 Alert history and predicted-alert shape

Use the existing alerts endpoint to display measured and predicted episodes:

```http
GET /api/alerts?pond_id=1&status=open&limit=100
Authorization: Bearer <access_token>
```

After migration 006, alert records include `source_type` and source-specific
references. For example, a predicted alert is returned as:

```json
{
  "items": [
    {
      "id": 91,
      "rule_id": 1,
      "device_id": "LOBSTER_CAGE_VANPHONG_01",
      "pond_id": 1,
      "source_type": "predicted",
      "severity": "warning",
      "status": "open",
      "first_reading_id": null,
      "last_reading_id": null,
      "first_prediction_id": 812,
      "last_prediction_id": 812,
      "opened_at": "2026-11-14T00:10:00Z",
      "last_observed_at": "2026-11-14T00:10:00Z",
      "resolved_at": null,
      "created_at": "2026-11-14T00:10:00Z",
      "updated_at": "2026-11-14T00:10:00Z",
      "first_value": 3.72,
      "last_value": 3.72,
      "worst_value": 3.72,
      "rule_snapshot": {
        "code": "low_do",
        "metric": "dissolved_oxygen",
        "version": 1,
        "warning_below": 4.0,
        "critical_below": 3.0,
        "recovery_above": 4.2
      },
      "acknowledged_at": null,
      "acknowledged_by": null
    }
  ],
  "next_cursor": null
}
```

For measured alerts, `source_type` is `"measured"`, reading references are
populated, and prediction references are `null`. Use `source_type` to label
the alert source; use `severity` (`warning` or `critical`) and `status`
(`open` or `resolved`) for badges and filters. Alert thresholds must be read
from `rule_snapshot` or `/api/alert-rules?pond_id=...`, not duplicated as
frontend constants. Values in this mock illustrate the development rule only.

`GET /api/alerts/{alert_id}` returns one alert object with the same fields.
Acknowledgment is `POST /api/alerts/{alert_id}/acknowledge`, requires Operator
or Admin, and has no request body. It returns:

```json
{
  "id": 91,
  "acknowledged_at": "2026-11-14T00:12:00Z",
  "acknowledged_by": "user:7"
}
```

### 3.5 Frontend types and fetch example

```ts
type Prediction = {
  id: number;
  source_reading_id: number | null;
  device_id: string;
  model_used: string;
  model_version: string | null;
  horizon_minutes: number | null;
  predicted_value: number;
  generated_at: string | null;
  target_at: string | null;
};

type Page<T> = {
  items: T[];
  next_cursor: number | null;
};

type LatestPredictions = {
  items: Prediction[];
  data_source: string;
};

type Alert = {
  id: number;
  rule_id: number;
  device_id: string;
  pond_id: number;
  source_type: "measured" | "predicted";
  severity: "warning" | "critical";
  status: "open" | "resolved";
  first_reading_id: number | null;
  last_reading_id: number | null;
  first_prediction_id: number | null;
  last_prediction_id: number | null;
  first_value: number;
  last_value: number;
  worst_value: number;
  opened_at: string;
  last_observed_at: string;
  resolved_at: string | null;
  rule_snapshot: Record<string, unknown>;
};

async function getLatestPredictions(
  apiBaseUrl: string,
  deviceId: string,
  accessToken: string,
): Promise<LatestPredictions> {
  const query = new URLSearchParams({ device_id: deviceId });
  const response = await fetch(
    `${apiBaseUrl}/api/predictions/latest?${query}`,
    { headers: { Authorization: `Bearer ${accessToken}` } },
  );
  if (!response.ok) {
    throw new Error(`Prediction request failed (${response.status})`);
  }
  return response.json();
}
```

Do not treat an empty prediction history as an error. On `401`, return to sign
in; show an empty/loading state for no records and an explicit retry state for
`503` or network failures. Cloud deployment must use the actual HTTPS API base
URL and allow the frontend origin in `API_ALLOWED_ORIGINS`.
