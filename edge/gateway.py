import logging
import os
import threading
import time
from pathlib import Path

from azure.iot.device import IoTHubDeviceClient, Message

from backend.telemetry import InvalidTelemetry, decode, encode
from edge.outbox import Outbox
from edge.mqtt import ROOT, load_settings, make_client

LOG = logging.getLogger("gateway")


def accept_message(topic, body, allowed_devices):
    payload = decode(body)
    if payload["device_id"] not in allowed_devices:
        raise InvalidTelemetry("Device is not in the gateway allowlist")
    if topic != f"lobster/{payload['device_id']}/telemetry":
        raise InvalidTelemetry("MQTT topic does not match device_id")
    return payload["message_id"], encode(payload)


def main():
    load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    allowed = {item.strip() for item in os.environ["GATEWAY_ALLOWED_DEVICES"].split(",") if item.strip()}
    daily_limit = int(os.getenv("GATEWAY_DAILY_UNITS", "500"))
    interval = float(os.getenv("GATEWAY_SEND_INTERVAL", "5"))
    if not allowed or not 1 <= daily_limit <= 6000 or interval < 1:
        raise ValueError("Require devices, daily units 1..6000, send interval >= 1")
    connection = os.environ["IOTHUB_DEVICE_CONNECTION_STRING"]
    fields = dict(part.split("=", 1) for part in connection.split(";") if "=" in part)
    if not fields.get("DeviceId") or fields.get("SharedAccessKeyName"):
        raise ValueError("Use a DEVICE connection string, never a Hub service policy")
    outbox = Outbox(Path(os.getenv("GATEWAY_OUTBOX", str(ROOT / ".runtime" / "outbox.sqlite3"))))
    fatal = threading.Event()
    ready = threading.Event()
    mqtt = make_client(os.getenv("GATEWAY_MQTT_CLIENT_ID", "lobster-gateway"), "GATEWAY", persistent=True)

    def on_connect(client, userdata, flags, rc):
        if rc != 0:
            LOG.error("MQTT connection rejected: %s", rc)
            fatal.set()
            return
        # Subscribe again on reconnect; persistent session retains queued QoS 1.
        for device in allowed:
            client.subscribe(f"lobster/{device}/telemetry", qos=1)

    def on_subscribe(client, userdata, mid, granted_qos):
        if 128 in granted_qos:
            fatal.set()
        else:
            ready.set()
            LOG.info("MQTT subscription ready")

    def on_message(client, userdata, msg):
        try:
            message_id, body = accept_message(msg.topic, msg.payload, allowed)
        except InvalidTelemetry as exc:
            LOG.warning("Rejected telemetry: %s", exc)
            return
        try:
            # Paho 1.x sends PUBACK after this callback returns. Commit first.
            outbox.enqueue(message_id, body)
        except Exception:
            LOG.error("Cannot persist telemetry; stopping before MQTT acknowledgement")
            fatal.set()
            client.disconnect()
            return
        LOG.info("Queued %s", message_id)

    mqtt.on_connect = on_connect
    mqtt.on_subscribe = on_subscribe
    mqtt.on_message = on_message
    mqtt.loop_start()
    azure = None
    failures = 0
    warned_budget = False
    try:
        if not ready.wait(20) or fatal.is_set():
            raise RuntimeError("MQTT subscription failed; check credentials/ACL")
        while not fatal.is_set():
            item = outbox.next()
            if not item:
                time.sleep(1)
                continue
            message_id, body = item
            if not outbox.reserve(body, daily_limit):
                if not warned_budget:
                    LOG.warning("Daily local budget exhausted; leaving messages queued until next UTC day")
                    warned_budget = True
                time.sleep(10)
                continue
            warned_budget = False
            try:
                if azure is None:
                    azure = IoTHubDeviceClient.create_from_connection_string(connection, connection_retry=False)
                    azure.connect()
                message = Message(body.decode("utf-8"))
                message.content_type = "application/json"
                message.content_encoding = "utf-8"
                message.message_id = message_id
                azure.send_message(message)
                outbox.mark_sent(message_id)
                failures = 0
                LOG.info("IoT Hub accepted %s", message_id)
            except Exception as exc:
                # Do not print SDK exception text: it can contain connection details.
                LOG.warning("Azure delivery failed (%s); retained for retry", type(exc).__name__)
                if azure:
                    try:
                        azure.shutdown()
                    except Exception:
                        pass
                azure = None
                failures += 1
                time.sleep(min(60, 2 ** min(failures, 6)))
            time.sleep(interval)
        raise RuntimeError("Gateway stopped after MQTT/persistence failure")
    except KeyboardInterrupt:
        LOG.info("Stopping; pending messages remain in SQLite")
    finally:
        mqtt.disconnect()
        mqtt.loop_stop()
        if azure:
            azure.shutdown()


if __name__ == "__main__":
    main()
