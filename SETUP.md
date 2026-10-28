# System Setup and Run Guide

## 1. Current Status and Data Flow

```text
CSV → simulator → local MQTT → gateway → Azure IoT Hub
    → Azure Function → Azure PostgreSQL ← FastAPI ← Swagger/frontend
```



## 2. Required Tools

| Tool | Purpose |
|---|---|
| Python 3.14 with pip/venv | Simulator, gateway, and API; matches the cloud runtime |
| Docker Desktop with Linux containers/WSL2 | MQTT and pgAdmin containers |
| Azure CLI (`az`) | Sign in to Azure and deploy App Service |
| Azure Functions Core Tools v4 (`func`) | Publish the ingestion Function |
| Web browser | Azure Portal, pgAdmin, and Swagger |


## 3. One-Time Project and Local Configuration

Start Docker Desktop and wait for the engine to become ready. In PowerShell:

```powershell
Set-Location C:\Projects\lobster-cage-monitoring
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If **neither** `.env.local` nor `.runtime/mqtt/passwords` exists, run:

```powershell
python -m edge.setup_mqtt
```

This creates both files with random MQTT credentials. Do not copy `.env.example`
to `.env.local` before this step. Skip it if credentials already exist. The tool
refuses to overwrite files; if only one file exists, restore the matching configuration
and password file rather than deleting active credentials or the outbox to retry.

Edit `.env.local` privately and fill in these values; do not commit the file:

| Group | Settings to check |
|---|---|
| MQTT | MQTT_HOST=127.0.0.1, MQTT_PORT=18884; generated username/password pairs |
| Gateway | GATEWAY_ALLOWED_DEVICES=LOBSTER_CAGE_VANPHONG_01 |
| IoT Hub | IOTHUB_DEVICE_CONNECTION_STRING from Devices → pond-gateway-01; must contain DeviceId=pond-gateway-01 |
| Sending limits | GATEWAY_SEND_INTERVAL=5, GATEWAY_DAILY_UNITS=500 |
| API/CLI database | PGHOST, PGPORT=5432, PGDATABASE set to the actual database |
| Local TLS | PGSSLROOTCERT=backend/certs/azure-postgresql-roots.pem |
| API database role | API_PGUSER=lobster_api, API_PGPASSWORD set to that role's password |
| JWT | Random AUTH_JWT_SECRET, AUTH_TOKEN_MINUTES=60 |
| Frontend origin | API_ALLOWED_ORIGINS=http://localhost:5173 if the frontend runs there |

Generate the JWT secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`
and paste it privately into the settings.

## 4. Prepare Azure and the Database Before Sending Data

If deployment is incomplete, follow [AZURE_IOT_SETUP.md](docs/AZURE_IOT_SETUP.md) for
IoT Hub, Storage, Functions, and PostgreSQL. See [ARCHITECTURE.md](ARCHITECTURE.md) for
settings and deployment commands. Do not recreate existing resources. 

## 5. Start Docker and Connect pgAdmin

```powershell
docker compose up -d
docker compose ps
```

Expect `mqtt` and `pgadmin` to be Up. MQTT listens on 127.0.0.1:18884; pgAdmin is at
http://localhost:5050. Compose currently sets the **pgAdmin UI account** to
`admin@lobster.farm` / `admin`; this is not a PostgreSQL or Dashboard account.

In pgAdmin, select Servers → Register → Server:

- General/Name: any display name, such as Azure Lobster.
- Connection/Host: the Azure PostgreSQL hostname, not localhost.
- Port: 5432; Maintenance database: the actual database, or postgres for administration.
- Username/password: PostgreSQL administrator for migrations, or `lobster_api` to read API data.
- SSL mode: verify-full; Root certificate: the CA file under `backend/certs/`.


## 6. Send Three Sensor Readings

Open each terminal at the project root and activate the virtual environment. Terminal A:

```powershell
python -m edge.gateway
```

Wait for `MQTT subscription ready`. In Terminal B:

```powershell
python -m edge.simulator --dry-run --limit 3
python -m edge.simulator --limit 3 --interval 5
```

Dry-run only validates payloads. The second command sends three rows. The simulator
prints step/message IDs; the gateway logs `Queued` and then `IoT Hub accepted`.
Hub acceptance does not prove a database write. The Function log
`Telemetry processed ... inserted=True` confirms the transaction.

Run this query in pgAdmin, then execute it again to refresh the results:

```sql
SELECT id, device_id, pond_id, timestamp, received_at,
       dissolved_oxygen, water_temperature, ph, salinity, turbidity, chlorophyll_a
FROM sensor_readings
WHERE device_id = 'LOBSTER_CAGE_VANPHONG_01'
ORDER BY received_at DESC NULLS LAST, id DESC LIMIT 10;
```

On the first send of previously unsent data, expect three rows. `timestamp` is the
CSV measurement time; `received_at` is the cloud receipt time. Replaying the same
rows does not add three more records because IDs are stable and duplicates are rejected.
To see new data, select a segment **not previously sent**, for example:

```powershell
python -m edge.simulator --start-row 3 --limit 3 --interval 5
```

start-row is zero-based. Do not delete the outbox to reset the quota. Check IoT Hub's
daily usage; the local budget of 500 is an estimate, not a replacement for F1 metering.
If no new rows appear, check MQTT → gateway → Function logs → DB permissions/firewall.
Rejected payloads go to the `telemetry-rejected` Blob container. Fixing a mapping
does not automatically replay old blobs. Readings older than the watermark do not
open or close alerts based on newer observations.

## 7. Are Dashboard Accounts Already Available?

The source **does not seed a default Dashboard username/password**. This guide cannot
determine which accounts you have created in Azure. Check as the owner in pgAdmin,
without retrieving password hashes:

```sql
SELECT id, username, role, enabled FROM users ORDER BY id;
```

If the account you need does not exist, run from the project root:

```powershell
python -m backend.manage_users create admin --role Admin
python -m backend.manage_users create farmer01 --role Operator
```

Existing accounts (username/password): `admin/admin_dashboard`; `farmer01/farmer01`

## 8. Run the Local Backend API on Port 9000

In Terminal C, at the root with the virtual environment activated:

```powershell
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 9000 --env-file .env.local
```

Open http://localhost:9000/api/health, then http://localhost:9000/api/docs:

## 9. Stop the Demo and Restart Later

- The simulator exits after reaching its limit. Stop the gateway and Uvicorn with Ctrl+C.
- `docker compose down`
