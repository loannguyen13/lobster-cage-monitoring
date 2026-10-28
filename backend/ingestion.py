import hashlib
import json
import logging
import os

import azure.functions as func
from azure.storage.blob import BlobServiceClient

from backend.database import connect
from backend.services.readings import save_reading
from backend.telemetry import InvalidTelemetry, decode


app = func.Blueprint()


def quarantine(body, gateway, reason):
    """Persist poison events before allowing checkpoint progress. No public blobs."""
    name = hashlib.sha256((gateway or "").encode() + b"\x00" + body).hexdigest() + ".json"
    service = BlobServiceClient.from_connection_string(os.environ["QUARANTINE_STORAGE_CONNECTION"])
    try:
        blob = service.get_blob_client(os.getenv("QUARANTINE_CONTAINER", "telemetry-rejected"), name)
        blob.upload_blob(json.dumps({"reason": reason, "gateway": gateway,
                                     "body": body.decode("utf-8", errors="replace")}), overwrite=True)
    finally:
        service.close()


@app.retry(strategy="fixed_delay", max_retry_count="-1", delay_interval="00:00:30")
@app.event_hub_message_trigger(arg_name="event", event_hub_name="%IOTHUB_EVENTHUB_NAME%",
                              connection="IOTHUB_EVENTS_CONNECTION",
                              consumer_group="%IOTHUB_CONSUMER_GROUP%", cardinality="one")
def ingest(event: func.EventHubEvent):
    body = event.get_body()
    # Trusted system metadata provided by the IoT Hub trigger, NOT JSON fields
    # or user-defined message properties. Missing metadata fails closed.
    gateway = (event.iothub_metadata or {}).get("connection-device-id")
    try:
        if not gateway:
            raise InvalidTelemetry("Missing authenticated IoT Hub device identity")
        payload = decode(body)
        connection = connect()
        try:
            with connection:
                inserted = save_reading(connection, payload, gateway)
        finally:
            connection.close()
        logging.info("Telemetry processed id=%s inserted=%s", payload["message_id"], inserted)
    except InvalidTelemetry as exc:
        quarantine(body, gateway, str(exc))
        logging.warning("Invalid telemetry persisted in quarantine: %s", exc)
    # DB/storage/configuration errors escape so the host retries. Infinite retry
    # deliberately pauses the affected partition instead of dropping readings.
