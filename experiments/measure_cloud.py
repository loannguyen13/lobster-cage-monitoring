"""Explicit, bounded cloud experiment; see docs/CLOUD_MEASUREMENT.md.

Default mode only validates the workload. No inference or research data changes.
"""
import argparse
import csv
import getpass
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid4, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.telemetry import encode
from edge.simulator import read_payloads


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def summarize(path):
    with path.open(encoding='utf-8', newline='') as source:
        rows = list(csv.DictReader(source))
    sent = [r for r in rows if r['kind'] == 'publish']
    seen = [r for r in rows if r['kind'] == 'seen']
    values = sorted(float(r['latency_s']) for r in seen)
    print(f'Attempted={len(sent)}, observed={len(seen)}, unobserved={len(sent)-len(seen)}')
    if values:
        percentile = lambda p: values[math.ceil(p * len(values)) - 1]
        print(f'Observed latency seconds: p50={percentile(.5):.3f}, p95={percentile(.95):.3f}')
        print(f'p99={percentile(.99):.3f} (exploratory when n < 1000)')
    if sent:
        deadline = float(sent[0]['deadline_s'])
        on_time = sum(float(r['latency_s']) <= deadline for r in seen)
        print(f'DTCR <= {deadline:g}s: {on_time}/{len(sent)} = {on_time/len(sent):.2%}')
    polls = [r for r in rows if r['kind'] == 'poll']
    valid = [float(r['aoi_s']) for r in polls if r['aoi_s']]
    print(f'AoI samples={len(valid)}/{len(polls)} polls; missing samples remain unknown.')
    if valid:
        valid.sort()
        print(f'Sampled AoI seconds: mean={sum(valid)/len(valid):.3f}, '
              f'p95={valid[math.ceil(.95*len(valid))-1]:.3f}, max={max(valid):.3f}')
        threshold = float(sent[0]['aoi_limit_s']) if sent else 0
        print(f'AoI <= {threshold:g}s: {sum(v <= threshold for v in valid)}/{len(polls)} '
              'poll observations (unknowns do not pass).')
    print('API errors:', sum(r['kind'] == 'poll' and r['status'] != '200' for r in rows))
    print('Run complete:', any(r['kind'] == 'end' for r in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', help='HTTPS App Service origin, without /api')
    parser.add_argument('--pond', type=int, default=1)
    parser.add_argument('--device', default='LOBSTER_CAGE_VANPHONG_01')
    parser.add_argument('--count', type=int, default=60)
    parser.add_argument('--interval', type=float, default=30)
    parser.add_argument('--poll', type=float, default=5)
    parser.add_argument('--deadline', type=float, default=15)
    parser.add_argument('--aoi-limit', type=float, default=45)
    parser.add_argument('--tail', type=float, default=60)
    parser.add_argument('--send-cloud', action='store_true')
    parser.add_argument('--summary', type=Path)
    args = parser.parse_args()
    if args.summary:
        summarize(args.summary)
        return
    if not (1 <= args.count <= 120 and args.interval >= 30 and args.poll >= 5
            and args.deadline > 0 and args.aoi_limit > 0 and args.tail >= args.deadline):
        parser.error('count 1..120, interval >=30, poll >=5, positive thresholds, tail >= deadline')
    payloads = read_payloads(ROOT / 'lobster_cage_water_quality_synthetic.csv', device=args.device)
    if len(payloads) < args.count:
        parser.error('Not enough source rows for the requested device/count')
    print(f'Workload: {args.count} messages; interval={args.interval}s; poll={args.poll}s.')
    print('Fresh synthetic measurement timestamps; source CSV is unchanged.')
    print('No-retry gateway budget estimate:', sum(
        math.ceil((len(encode(p)) + 512) / 512) for p in payloads[:args.count]))
    if not args.send_cloud:
        print('DRY RUN: no MQTT or HTTP calls. Add --send-cloud only after following the guide.')
        return
    parsed = urlparse(args.api or '')
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        parser.error('--api must be your HTTPS cloud origin, without credentials/path/query')

    import httpx
    from edge.mqtt import load_settings, make_client

    load_settings()
    print('Use an application account created with backend.manage_users, not a PostgreSQL/Azure login.')
    username = input('Dashboard/API username: ')
    password = getpass.getpass('Dashboard/API password (not saved): ')
    run_id = str(uuid4())
    output = ROOT / '.runtime' / 'evaluation' / f'{run_id}.csv'
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ['run_id', 'kind', 'at_utc', 'elapsed_s', 'device_id', 'message_id',
              'source_timestamp', 'measured_at', 'reading_id', 'status', 'latency_s',
              'aoi_s', 'request_s', 'interval_s', 'poll_s', 'deadline_s', 'aoi_limit_s', 'note',
              'request_id', 'server_timing']
    pending = {}
    observed = set()
    start = time.perf_counter()
    mqtt = None
    with output.open('x', encoding='utf-8', newline='') as target, httpx.Client(
            base_url=args.api.rstrip('/'), timeout=10, follow_redirects=False) as client:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()

        def log(kind, **values):
            writer.writerow(dict(run_id=run_id, kind=kind, at_utc=utc_now(),
                                 elapsed_s=time.perf_counter()-start, device_id=args.device,
                                 interval_s=args.interval, poll_s=args.poll,
                                 deadline_s=args.deadline, aoi_limit_s=args.aoi_limit, **values))
            target.flush()

        def signin():
            try:
                response = client.post('/api/auth/signin',
                                       json={'username': username, 'password': password}, timeout=60)
            except httpx.TimeoutException:
                raise SystemExit('Signin timed out after waiting up to 60s for network activity. '
                                 'This does not establish that the password is wrong. '
                                 'Check cloud /api/health, /api/docs, and App Service/DB logs; then retry.') from None
            except httpx.HTTPError:
                raise SystemExit('Cannot reach the HTTPS signin endpoint. Check the cloud URL, '
                                 'network and TLS configuration.') from None
            if response.status_code != 200:
                detail = (' Check the Dashboard/API account, password, enabled status or temporary lock.'
                          if response.status_code == 401 else ' Check App Service configuration and logs.')
                raise SystemExit(f'Signin failed: HTTP {response.status_code}.' + detail)
            data = response.json()
            client.headers['Authorization'] = 'Bearer ' + data['access_token']
            return time.perf_counter() + max(1, data['expires_in'] - 60)

        try:
            renew_at = signin()
            mqtt = make_client('cloud-metrics-' + run_id[:8], 'SIMULATOR')
            mqtt.loop_start()
            log('start', note=f'api={args.api}; pond={args.pond}; count={args.count}; tail={args.tail}')
            next_send = next_poll = time.perf_counter()
            sent = 0
            finish = None
            while finish is None or time.perf_counter() < finish:
                now = time.perf_counter()
                if now >= renew_at:
                    renew_at = signin()
                if sent < args.count and now >= next_send:
                    original = payloads[sent]
                    payload = dict(original)
                    payload['timestamp'] = utc_now()
                    payload['message_id'] = str(uuid5(NAMESPACE_URL,
                        f"lobster:v1:{args.device}:{payload['timestamp']}"))
                    body = encode(payload)
                    published = time.perf_counter()
                    key = datetime.fromisoformat(payload['timestamp'])
                    pending[key] = (published, payload['message_id'])
                    log('publish', message_id=payload['message_id'], source_timestamp=original['timestamp'],
                        measured_at=payload['timestamp'], note=f'bytes={len(body)}')
                    info = mqtt.publish(f'lobster/{args.device}/telemetry', body, qos=1, retain=False)
                    info.wait_for_publish(timeout=15)
                    log('mqtt_ack', message_id=payload['message_id'], status=str(info.is_published()))
                    sent += 1
                    next_send = published + args.interval
                    if sent == args.count:
                        finish = published + args.tail
                if time.perf_counter() >= next_poll:
                    before = time.perf_counter()
                    try:
                        response = client.get('/api/readings/latest', params={'pond_id': args.pond},
                                              headers={'Cache-Control': 'no-cache'})
                        after = time.perf_counter()
                        if response.status_code != 200:
                            log('poll', status=str(response.status_code), request_s=after-before,
                                request_id=response.headers.get('X-Request-ID', ''),
                                server_timing=response.headers.get('Server-Timing', ''))
                        else:
                            item = next((r for r in response.json()['items'] if r['device_id'] == args.device), None)
                            stamp = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00')) if item and item['timestamp'] else None
                            age = (datetime.now(timezone.utc)-stamp).total_seconds() if stamp else None
                            log('poll', status='200', request_s=after-before,
                                request_id=response.headers.get('X-Request-ID', ''),
                                server_timing=response.headers.get('Server-Timing', ''),
                                measured_at=stamp.isoformat() if stamp else '',
                                reading_id=item.get('reading_id', '') if item else '',
                                aoi_s=age if age is not None and age >= 0 else '',
                                note='missing/future timestamp' if age is None or age < 0 else '')
                            if stamp in pending and stamp not in observed:
                                published, message_id = pending[stamp]
                                log('seen', message_id=message_id, measured_at=stamp.isoformat(),
                                    reading_id=item['reading_id'], latency_s=after-published)
                                observed.add(stamp)
                    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                        log('poll', status=type(exc).__name__)
                    next_poll = time.perf_counter() + args.poll
                time.sleep(.05)
            log('end')
        finally:
            if mqtt:
                mqtt.disconnect()
                mqtt.loop_stop()
            if 'Authorization' in client.headers:
                try:
                    client.post('/api/auth/logout')
                except httpx.HTTPError:
                    pass
            print('Trace:', output)
    summarize(output)


if __name__ == '__main__':
    main()
