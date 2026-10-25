import type { Alert, Reading, Severity } from "@/types";

export function levelOf(d: number): Severity | null {
  return d < 3 ? "critical" : d < 4 ? "warning" : null;
}

// Gộp các điểm liên tiếp cùng mức thành một đợt cảnh báo, mới nhất lên đầu
export function buildAlerts(rs: Reading[]): Alert[] {
  const out: Alert[] = [];
  let cur: Alert | null = null;
  for (const r of rs) {
    const lv = levelOf(r.do);
    if (!lv) { cur = null; continue; }
    if (cur && cur.level === lv) {
      cur.end = r.timestamp;
      cur.minDO = Math.min(cur.minDO, r.do);
      cur.points++;
    } else {
      cur = {
        id: `${r.timestamp}-${lv}`, start: r.timestamp, end: r.timestamp,
        level: lv, minDO: r.do, points: 1,
        message: lv === "critical" ? "DO < 3.0 mg/L" : "DO < 4.0 mg/L",
      };
      out.push(cur);
    }
  }
  return out.reverse();
}