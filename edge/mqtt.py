import os
import ssl
from pathlib import Path

from dotenv import load_dotenv
import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[1]


def load_settings():
    load_dotenv(ROOT / ".env.local", override=False)


def make_client(client_id, role, persistent=False):
    # Azure IoT Device SDK 2.x requires Paho 1.x.
    client = mqtt.Client(client_id=client_id, clean_session=not persistent)
    username = os.environ[f"MQTT_{role}_USERNAME"]
    password = os.environ[f"MQTT_{role}_PASSWORD"]
    if not username or not password:
        raise ValueError("MQTT credentials must not be empty")
    client.username_pw_set(username, password)
    host = os.getenv("MQTT_HOST", "127.0.0.1")
    ca = os.getenv("MQTT_CA_FILE")
    if ca:
        client.tls_set(ca_certs=ca, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    elif host not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("MQTT_CA_FILE is required for non-loopback MQTT")
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(host, int(os.getenv("MQTT_PORT", "18884")), keepalive=60)
    return client
