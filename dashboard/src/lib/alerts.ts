import type { Alert, AlertSource, Severity, Thresholds } from "@/types";

// Giá trị mặc định (trùng luật low_do hiện tại); khi có API sẽ dùng ngưỡng đọc từ /api/alert-rules
export const DEFAULT_THRESHOLDS: Thresholds = { warning: 4, critical: 3, recovery: 4.2 };

export function levelOf(d: number, t: Thresholds = DEFAULT_THRESHOLDS): Severity | null {
  if (Number.isNaN(d)) return null;
  return d < t.critical ? "critical" : d < t.warning ? "warning" : null;
}

type Point = { timestamp: string; value: number };

// Gộp các điểm liên tiếp thành từng đợt cảnh báo, có độ trễ phục hồi:
// đợt mở khi DO xuống dưới ngưỡng cảnh báo, mức độ là mức nặng nhất trong đợt,
// và chỉ đóng khi DO lên tới mức phục hồi (recovery) trở lên.
export function buildAlerts(
  points: Point[],
  t: Thresholds = DEFAULT_THRESHOLDS,
  source: AlertSource = "measured"
): Alert[] {
  const out: Alert[] = [];
  let cur: Alert | null = null;
  const label = source === "predicted" ? "DO dự báo" : "DO";
  const msg = (lv: Severity) => `${label} < ${lv === "critical" ? t.critical : t.warning} mg/L`;

  for (const p of points) {
    if (Number.isNaN(p.value)) continue;
    const lv = levelOf(p.value, t);
    if (lv) {
      if (!cur) {
        cur = {
          id: `${source}-${p.timestamp}`, start: p.timestamp, end: "", level: lv,
          minDO: p.value, points: 1, message: msg(lv), source, status: "open",
        };
        out.push(cur);
      } else {
        cur.points += 1;
        cur.minDO = Math.min(cur.minDO, p.value);
        if (lv === "critical" && cur.level !== "critical") {
          cur.level = "critical";
          cur.message = msg("critical");
        }
      }
    } else if (cur) {
      if (p.value >= t.recovery) {
        cur.end = p.timestamp;
        cur.status = "resolved";
        cur = null;
      } else {
        cur.points += 1; // vùng giữa ngưỡng cảnh báo và mức phục hồi: chưa đóng đợt
      }
    }
  }
  return out.reverse();
}
