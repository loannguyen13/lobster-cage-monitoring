import type { Alert, ChartPoint, Prediction, Reading, Severity } from "@/types";

export type Raw = Record<string, unknown>;

function isObj(v: unknown): v is Raw {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

// Lấy giá trị của key đầu tiên có mặt
export function pick(o: Raw, ...keys: string[]): unknown {
  for (const k of keys) {
    const v = o[k];
    if (v !== undefined && v !== null) return v;
  }
  return undefined;
}

export function numOr(v: unknown): number | undefined {
  if (v === undefined || v === null || v === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

const LIST_KEYS = [
  "items", "data", "results", "readings", "alerts",
  "ponds", "devices", "predictions",
];

// API có thể trả mảng, hoặc {items: [...]}, hoặc một object đơn
export function asList(x: unknown): Raw[] {
  if (Array.isArray(x)) return x.filter(isObj);
  if (isObj(x)) {
    for (const k of LIST_KEYS) {
      const v = x[k];
      if (Array.isArray(v)) return v.filter(isObj);
    }
    return [x];
  }
  return [];
}

export const ms = (ts: string) => Date.parse(ts);

export const sortAsc = (rs: Reading[]) =>
  [...rs].sort((a, b) => ms(a.timestamp) - ms(b.timestamp));

// Chuyển JSON của backend thành Reading (nhận cả tên cột trong database)
export function toReading(raw: Raw): Reading | null {
  const timestamp = pick(raw, "timestamp", "measured_at", "time", "recorded_at");
  if (typeof timestamp !== "string" || Number.isNaN(ms(timestamp))) return null;
  const n = (...keys: string[]) => numOr(pick(raw, ...keys)) ?? NaN;
  return {
    device_id: String(pick(raw, "device_id") ?? ""),
    timestamp,
    temperature: n("temperature", "water_temperature"),
    ph: n("ph"),
    do: n("do", "dissolved_oxygen"),
    salinity: n("salinity"),
    turbidity: n("turbidity"),
    chlorophyll_a: n("chlorophyll_a"),
    event_label: pick(raw, "event_label") as Reading["event_label"],
    do_pred_15m: numOr(pick(raw, "do_pred_15m")),
  };
}

export function toPrediction(raw: Raw): Prediction | null {
  const target = pick(
    raw, "target_at", "target_time", "predicted_for", "forecast_time", "timestamp"
  );
  if (typeof target !== "string" || Number.isNaN(ms(target))) return null;
  let value = numOr(pick(
    raw, "predicted_do", "predicted_value", "predicted_dissolved_oxygen",
    "prediction", "predicted", "do_pred", "do_pred_15m", "value"
  ));
  if (value === undefined) {
    for (const [k, v] of Object.entries(raw)) {
      if (/pred|forecast/i.test(k) && !/(_at|time|id|model|version|label|status|horizon)/i.test(k)) {
        const n = numOr(v);
        if (n !== undefined) { value = n; break; }
      }
    }
  }
  if (value === undefined) return null;
  const model = pick(raw, "model_used", "model");
  return { target_at: target, value, model: model === undefined ? undefined : String(model) };
}

export function toAlert(raw: Raw, index = 0): Alert {
  const start = String(
    pick(raw, "opened_at", "started_at", "start_time", "triggered_at", "created_at", "timestamp") ?? ""
  );
  const status = String(pick(raw, "status") ?? "");
  const end = /open/i.test(status)
    ? ""
    : String(pick(raw, "resolved_at", "closed_at", "ended_at", "last_seen_at", "updated_at") ?? start);
  const sev = String(pick(raw, "severity", "level") ?? "").toLowerCase();
  const level: Severity = /crit|high|severe|danger|nguy/.test(sev) ? "critical" : "warning";
  return {
    id: String(pick(raw, "id", "alert_id") ?? index),
    start, end, level,
    message: String(pick(raw, "message", "title", "rule_name", "description") ?? "Cảnh báo"),
    minDO: numOr(pick(raw, "min_value", "peak_value", "trigger_value", "observed_value", "value")) ?? NaN,
    points: 1,
  };
}

// Ghép DO dự báo vào các điểm đo thật (khớp thời gian ±2,5 phút),
// dự báo cho tương lai chưa có số đo thì thêm điểm chỉ có dự báo.
export function mergePredictions(readings: Reading[], preds: Prediction[]): ChartPoint[] {
  const points = new Map<number, ChartPoint>();
  for (const r of readings) points.set(ms(r.timestamp), { ...r });
  const times = [...points.keys()];
  const first = times.length ? Math.min(...times) : -Infinity;

  for (const p of preds) {
    const t = ms(p.target_at);
    if (t < first) continue;
    let best: number | undefined;
    for (const k of times) {
      if (Math.abs(k - t) <= 150000 && (best === undefined || Math.abs(k - t) < Math.abs(best - t))) best = k;
    }
    const point = best === undefined ? undefined : points.get(best);
    if (point) point.do_pred_15m = p.value;
    else points.set(t, { timestamp: p.target_at, do_pred_15m: p.value });
  }
  return [...points.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v);
}

// Thêm điểm mới vào cửa sổ dữ liệu
export function appendReading(prev: Reading[], r: Reading, windowSize: number): Reading[] {
  const last = prev[prev.length - 1];
  if (!last) return [r];
  const t = ms(r.timestamp);
  const lt = ms(last.timestamp);
  if (t === lt) return prev;
  if (t < lt) {
    // Dữ liệu quay về thời điểm sớm hơn = một kịch bản mới vừa bắt đầu
    return prev.some((x) => ms(x.timestamp) === t) ? prev : [r];
  }
  return [...prev, r].slice(-windowSize);
}
