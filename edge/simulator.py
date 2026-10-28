import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from backend.telemetry import FEATURES, encode, validate
from edge.mqtt import ROOT, load_settings, make_client


def read_payloads(path, source_timezone="Asia/Ho_Chi_Minh", device=None):
    """Preflight the whole CSV before publishing anything; preserve source time."""
    previous = {}
    payloads = []
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not {"device_id", "timestamp", *FEATURES} <= set(reader.fieldnames or []):
            raise ValueError("CSV does not contain the lobster telemetry columns")
        for row in reader:
            if device and row["device_id"] != device:
                continue
            measured = datetime.fromisoformat(row["timestamp"])
            if measured.utcoffset() is None:
                measured = measured.replace(tzinfo=ZoneInfo(source_timezone))
            measured = measured.astimezone(timezone.utc)
            device_id = row["device_id"]
            if device_id in previous and measured <= previous[device_id]:
                raise ValueError(f"Non-increasing timestamp for {device_id}")
            previous[device_id] = measured
            timestamp = measured.isoformat().replace("+00:00", "Z")
            # Stable across retries/replays. A changed measurement at the same
            # device/time is a conflict to investigate, not a new observation.
            message_id = str(uuid5(NAMESPACE_URL, f"lobster:v1:{device_id}:{timestamp}"))
            payloads.append(validate({"schema_version": 1, "message_id": message_id,
                                      "device_id": device_id, "timestamp": timestamp,
                                      "readings": {key: float(row[key]) for key in FEATURES}}))
    if not payloads:
        raise ValueError("No matching dataset rows")
    return sorted(payloads, key=lambda item: (
        datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")), item["device_id"]
    ))


def main():
    parser = argparse.ArgumentParser(description="Bounded replay of lobster CSV telemetry")
    parser.add_argument("--csv", type=Path, default=ROOT / "lobster_cage_water_quality_synthetic.csv")
    parser.add_argument("--source-timezone", default="Asia/Ho_Chi_Minh")
    parser.add_argument("--device")
    parser.add_argument("--start-row", type=int, default=0)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scenario", choices=["normal", "intermittent-connection", "missing-data"], default="normal")
    parser.add_argument("--drop-every", type=int, default=8)
    parser.add_argument("--missing-sensor", choices=FEATURES, default="do")
    args = parser.parse_args()
    if args.limit < 1 or args.start_row < 0 or args.interval < 1 or args.drop_every < 1:
        parser.error("limit/drop-every >= 1, start-row >= 0, interval >= 1 second")
    payloads = read_payloads(args.csv, args.source_timezone, args.device)
    payloads = payloads[args.start_row:args.start_row + args.limit]
    if not payloads:
        parser.error("start-row is outside the selected dataset")
    load_settings()
    client = None
    if not args.dry_run:
        client = make_client("lobster-simulator", "SIMULATOR")
        client.loop_start()
    try:
        for index, payload in enumerate(payloads, 1):
            if args.scenario == "intermittent-connection" and index % args.drop_every == 0:
                print(f"step={index} simulated missing transmission")
            else:
                body = encode(payload)
                if args.scenario == "missing-data":
                    del payload["readings"][args.missing_sensor]
                    body = json.dumps(payload, separators=(",", ":")).encode()
                if client:
                    info = client.publish(f"lobster/{payload['device_id']}/telemetry", body, qos=1, retain=False)
                    info.wait_for_publish(timeout=15)
                    if not info.is_published():
                        raise RuntimeError("MQTT publish was not acknowledged; stop replay")
                print(f"step={index} id={payload['message_id']} bytes={len(body)} timestamp={payload['timestamp']}")
            if client and index < len(payloads):
                time.sleep(args.interval)
    finally:
        if client:
            client.disconnect()
            client.loop_stop()


if __name__ == "__main__":
    main()
