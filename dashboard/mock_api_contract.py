"""API giả theo đúng hợp đồng trong API.md (đăng nhập, ao, thiết bị, số liệu, dự báo, cảnh báo, luật).
Dùng để thử giao diện khi backend chưa có dữ liệu dự báo.

Chạy (không cần cài thêm gì), đặt file ở thư mục gốc dashboard (cùng cấp package.json):
    python mock_api_contract.py                    # có dự báo và cảnh báo
    python mock_api_contract.py --no-predictions   # dự báo rỗng: thử trạng thái trống
    python mock_api_contract.py --fail-predictions # dự báo trả 503: thử trạng thái lỗi
Tài khoản thử: demo / demo. Cổng mặc định 8000.
Trong .env.local của dashboard:  NEXT_PUBLIC_API_URL=http://localhost:8000

Giống API thật: /api/readings và /api/predictions chỉ trả trong 24 giờ gần nhất nếu thiếu from/to.
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent
SRC = BASE / "src" / "lib" / "mockScenarios.json"
if not SRC.exists():
    SRC = BASE / "mockScenarios.json"

PORT = 8000
NO_PRED = "--no-predictions" in sys.argv
FAIL_PRED = "--fail-predictions" in sys.argv
TOKEN = "mock.jwt.token"
DEVICE, POND = "LOBSTER_CAGE_VANPHONG_01", 1
RULE = {"code": "low_do", "metric": "dissolved_oxygen", "version": 1,
        "warning_below": 4.0, "critical_below": 3.0, "recovery_above": 4.2}

# ----- dữ liệu: cửa sổ thiếu oxy, giờ đo (giờ VN) đổi sang UTC như simulator thật -----
raw = json.loads(SRC.read_text(encoding="utf-8"))["oxygen_deficit"]
UTC = timezone.utc
VN = timezone(timedelta(hours=7))


def iso(dt):
    return dt.astimezone(UTC).isoformat()


readings = []
for i, r in enumerate(raw):
    ts = datetime.fromisoformat(r["timestamp"]).replace(tzinfo=VN)
    readings.append({
        "reading_id": i + 1, "device_id": DEVICE, "pond_id": POND, "_ts": ts,
        "timestamp": iso(ts), "received_at": iso(ts + timedelta(minutes=1)),
        "dissolved_oxygen": r["do"], "ph": r["ph"], "water_temperature": r["temperature"],
        "salinity": r["salinity"], "turbidity": r["turbidity"], "chlorophyll_a": r["chlorophyll_a"],
    })

# ----- dự báo: với mỗi số đo thật tạo dự báo +15 phút của xgboost và persistence -----
rnd = random.Random(7)
predictions, pid = [], 0
n = len(readings)
for i, r in enumerate(readings):
    future = readings[min(i + 3, n - 1)]["dissolved_oxygen"]
    for model, value in (("persistence", r["dissolved_oxygen"]),
                         ("xgboost", 0.85 * future + 0.15 * r["dissolved_oxygen"] + rnd.gauss(0, 0.1))):
        pid += 1
        predictions.append({
            "id": pid, "source_reading_id": r["reading_id"], "device_id": DEVICE,
            "model_used": model, "model_version": f"{model}-do-15m-v1", "horizon_minutes": 15,
            "predicted_value": round(value, 2),
            "generated_at": iso(r["_ts"] + timedelta(minutes=1)),
            "target_at": iso(r["_ts"] + timedelta(minutes=15)), "_target": r["_ts"] + timedelta(minutes=15),
        })


# ----- cảnh báo: gộp đợt, có độ trễ phục hồi -----
def episodes(points, source):
    out, cur = [], None
    for ts, value, ref in points:
        sev = "critical" if value < RULE["critical_below"] else "warning" if value < RULE["warning_below"] else None
        if sev:
            if cur is None:
                cur = {"severity": sev, "first": (ts, value, ref), "last": (ts, value, ref), "worst": value}
                out.append(cur)
            else:
                cur["last"] = (ts, value, ref)
                cur["worst"] = min(cur["worst"], value)
                if sev == "critical":
                    cur["severity"] = "critical"
        elif cur is not None:
            if value >= RULE["recovery_above"]:
                cur["resolved"] = ts
                cur = None
            else:
                cur["last"] = (ts, value, ref)
    alerts = []
    for k, e in enumerate(out):
        meas = source == "measured"
        alerts.append({
            "source_type": source, "severity": e["severity"],
            "status": "resolved" if "resolved" in e else "open",
            "first_reading_id": e["first"][2] if meas else None, "last_reading_id": e["last"][2] if meas else None,
            "first_prediction_id": None if meas else e["first"][2], "last_prediction_id": None if meas else e["last"][2],
            "opened_at": iso(e["first"][0]), "last_observed_at": iso(e["last"][0]),
            "resolved_at": iso(e["resolved"]) if "resolved" in e else None,
            "first_value": e["first"][1], "last_value": e["last"][1], "worst_value": e["worst"],
        })
    return alerts


def build_alerts():
    items = episodes([(r["_ts"], r["dissolved_oxygen"], r["reading_id"]) for r in readings], "measured")
    if not NO_PRED:
        items += episodes([(p["_target"], p["predicted_value"], p["id"])
                           for p in predictions if p["model_used"] == "xgboost"], "predicted")
    items.sort(key=lambda a: a["opened_at"])
    for k, a in enumerate(items, 1):
        a.update({"id": k, "rule_id": 1, "device_id": DEVICE, "pond_id": POND,
                  "created_at": a["opened_at"], "updated_at": a["last_observed_at"],
                  "rule_snapshot": RULE, "acknowledged_at": None, "acknowledged_by": None})
    return list(reversed(items))  # id giảm dần


ALERTS = build_alerts()


def clean(rows):
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


class Err(Exception):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail


def parse_dt(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "+"))
    except ValueError:
        raise Err(422, "from/to không hợp lệ")
    if dt.tzinfo is None:
        raise Err(422, "from/to phải có múi giờ")
    return dt


def window(q):
    now = datetime.now(UTC)
    frm = parse_dt(q["from"][0]) if "from" in q else now - timedelta(hours=24)
    to = parse_dt(q["to"][0]) if "to" in q else now
    if to <= frm or to - frm > timedelta(days=7):
        raise Err(422, "khoảng thời gian phải dương và không quá 7 ngày")
    return frm, to


def paginate(rows, q):
    try:
        limit = int(q.get("limit", ["100"])[0])
        cursor = int(q["cursor"][0]) if "cursor" in q else None
    except ValueError:
        raise Err(422, "limit/cursor không hợp lệ")
    if not 1 <= limit <= 1000 or (cursor is not None and cursor <= 0):
        raise Err(422, "limit từ 1 đến 1000, cursor phải dương")
    rows = sorted(rows, key=lambda r: r.get("id", r.get("reading_id")), reverse=True)
    key = "id" if "id" in rows[0] else "reading_id" if rows else "id"
    if cursor is not None:
        rows = [r for r in rows if r[key] < cursor]
    page = rows[:limit]
    nxt = page[-1][key] if len(rows) > limit else None
    return clean(page), nxt


def need(q, name):
    if name not in q:
        raise Err(422, f"thiếu tham số {name}")
    return q[name][0]


def route(method, path, q, body, auth):
    if method == "GET" and path == "/api/health":
        return 200, {"status": "ok"}
    if method == "POST" and path == "/api/auth/signin":
        if body.get("username") == "demo" and body.get("password") == "demo":
            return 200, {"access_token": TOKEN, "token_type": "bearer", "expires_in": 3600}
        return 401, {"detail": "Invalid credentials"}
    if auth != f"Bearer {TOKEN}":
        return 401, {"detail": "Invalid credentials or inactive session"}

    last = readings[-1]
    if method == "POST" and path == "/api/auth/logout":
        return 204, None
    if method == "GET" and path == "/api/auth/me":
        return 200, {"id": 2, "username": "demo", "role": "Operator"}
    if method == "GET" and path == "/api/ponds":
        return 200, {"items": [{"id": POND, "name": "Van Phong - cage 01", "status": "active", "metadata": None}]}
    if method == "GET" and path == "/api/devices":
        need(q, "pond_id")
        return 200, {"items": [{"device_id": DEVICE, "pond_id": POND, "display_name": None, "enabled": True,
                                "expected_interval_seconds": 300, "last_received_at": last["received_at"],
                                "last_measured_at": last["timestamp"]}]}
    if method == "GET" and path == "/api/readings/latest":
        need(q, "pond_id")
        row = {k: v for k, v in last.items() if not k.startswith("_")}
        row.update({"display_name": None, "enabled": True, "reception_stale": True, "measurement_stale": True})
        return 200, {"items": [row], "data_source": "synthetic_replay"}
    if method == "GET" and path == "/api/readings":
        if need(q, "device_id") != DEVICE:
            return 404, {"detail": "device not found"}
        frm, to = window(q)
        rows = [r for r in readings if frm <= r["_ts"] < to]
        if not rows:
            return 200, {"items": [], "next_cursor": None}
        page, nxt = paginate(rows, q)
        return 200, {"items": page, "next_cursor": nxt}
    if method == "GET" and path == "/api/dashboard":
        need(q, "pond_id")
        return 200, {"pond_id": POND, "latest": {"items": [{k: v for k, v in last.items() if not k.startswith("_")}]},
                     "open_alerts": {}, "data_source": "synthetic_replay"}
    if method == "GET" and path == "/api/alert-rules":
        need(q, "pond_id")
        return 200, {"items": [{"id": 1, "pond_id": POND, **{k: RULE[k] for k in ("code", "metric", "warning_below", "critical_below", "recovery_above")},
                                "enabled": True, "version": 1}]}
    if method == "GET" and path == "/api/alerts":
        need(q, "pond_id")
        rows = ALERTS
        if "status" in q:
            rows = [a for a in rows if a["status"] == q["status"][0]]
        if not rows:
            return 200, {"items": [], "next_cursor": None}
        page, nxt = paginate(rows, q)
        return 200, {"items": page, "next_cursor": nxt}
    if method == "GET" and path.startswith("/api/predictions"):
        if need(q, "device_id") != DEVICE:
            return 404, {"detail": "device not found"}
        if FAIL_PRED:
            return 503, {"detail": "prediction service unavailable"}
        if path == "/api/predictions/latest":
            if NO_PRED:
                return 200, {"items": [], "data_source": "synthetic_replay"}
            newest = {}
            for p in predictions:
                newest[p["model_used"]] = p
            return 200, {"items": clean(sorted(newest.values(), key=lambda p: p["id"], reverse=True)),
                         "data_source": "synthetic_replay"}
        if path == "/api/predictions":
            frm, to = window(q)
            rows = [] if NO_PRED else [p for p in predictions if frm <= p["_target"] < to]
            if not rows:
                return 200, {"items": [], "next_cursor": None}
            page, nxt = paginate(rows, q)
            return 200, {"items": page, "next_cursor": nxt}
    return 404, {"detail": "not found"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=None):
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        if body is None:
            self.end_headers()
            return
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self, method):
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}") if method == "POST" else {}
        except json.JSONDecodeError:
            body = {}
        try:
            code, payload = route(method, url.path, parse_qs(url.query), body, self.headers.get("Authorization", ""))
        except Err as e:
            code, payload = e.code, {"detail": e.detail}
        self._send(code, payload)

    def do_OPTIONS(self):
        self._send(204)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def log_message(self, fmt, *args):
        print(self.address_string(), fmt % args)


mode = "không có dự báo" if NO_PRED else "dự báo lỗi 503" if FAIL_PRED else "có dự báo và cảnh báo"
print(f"API giả ({mode}) tại http://localhost:{PORT}  | tài khoản demo / demo | dừng bằng Ctrl+C")
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
