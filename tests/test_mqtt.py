"""Opt-in local broker integration; never connects to Azure."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from uuid import uuid4

import paho.mqtt.client as mqtt

from edge.gateway import accept_message
from edge.outbox import Outbox
from edge.mqtt import load_settings, make_client
from edge.simulator import ROOT, read_payloads
from backend.telemetry import encode
from edge.sensor_telemetry import split_reading, topic_for, encode as encode_sensor
from edge.aggregation import SensorAggregator


@unittest.skipUnless(os.getenv("LOBSTER_TEST_MQTT") == "1", "requires configured local MQTT broker")
class MqttTests(unittest.TestCase):
    def test_qos1_authenticated_roundtrip_and_durable_enqueue(self):
        load_settings()
        payload = read_payloads(ROOT / "lobster_cage_water_quality_synthetic.csv")[0]
        # A fresh event time isolates this roundtrip while preserving stable aggregate IDs.
        from datetime import datetime, timezone
        from edge.sensor_telemetry import cloud_message_id
        payload['timestamp'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        payload['message_id'] = cloud_message_id(payload['device_id'], payload['timestamp'])
        ready, received = threading.Event(), threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            outbox = Outbox(Path(directory) / "mqtt.sqlite3")
            aggregator = SensorAggregator(outbox)
            subscriber = make_client("test-gateway-" + uuid4().hex, "GATEWAY")
            subscriber.on_connect = lambda c, u, f, rc: c.subscribe(f"lobster/{payload['device_id']}/sensors/+", qos=1)
            subscriber.on_subscribe = lambda *args: ready.set()
            def receive(client, userdata, message):
                sensor = accept_message(message.topic, message.payload, {payload["device_id"]})
                if sensor['timestamp'] == payload['timestamp']:
                    if aggregator.accept(sensor) == 'queued':
                        received.set()
            subscriber.on_message = receive
            subscriber.loop_start()
            publisher = None
            try:
                self.assertTrue(ready.wait(10), "subscription timeout")
                publisher = make_client("test-simulator-" + uuid4().hex, "SIMULATOR")
                publisher.loop_start()
                for sensor in reversed(list(split_reading(payload))):
                    info = publisher.publish(topic_for(sensor), encode_sensor(sensor), qos=1, retain=False)
                    info.wait_for_publish(10)
                    self.assertTrue(info.is_published())
                self.assertTrue(received.wait(10))
                self.assertEqual(outbox.next()[0], payload["message_id"])
                self.assertEqual(outbox.next()[1], encode(payload))
            finally:
                if publisher:
                    publisher.disconnect()
                    publisher.loop_stop()
                subscriber.disconnect()
                subscriber.loop_stop()

    def test_anonymous_connection_rejected(self):
        load_settings()
        done = threading.Event()
        codes = []
        client = mqtt.Client("anonymous-test-" + uuid4().hex)
        def connected(c, u, flags, rc):
            codes.append(rc)
            done.set()
        client.on_connect = connected
        client.connect("127.0.0.1", int(os.getenv("MQTT_PORT", "18884")))
        client.loop_start()
        try:
            self.assertTrue(done.wait(10))
            self.assertNotEqual(codes[0], 0)
        finally:
            client.disconnect()
            client.loop_stop()
