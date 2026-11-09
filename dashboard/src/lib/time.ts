const HAS_TZ = /(Z|[+-]\d{2}:?\d{2})$/;

// Giờ có múi giờ (từ API, dạng UTC) đổi sang giờ Việt Nam (UTC+7).
// Giờ không có múi giờ (dữ liệu mock) giữ nguyên.
export function fmtTime(t: unknown): string {
  const s = String(t);
  if (!HAS_TZ.test(s)) return s.slice(5, 16).replace("T", " ");
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return new Date(d.getTime() + 7 * 3600000)
    .toISOString()
    .slice(5, 16)
    .replace("T", " ");
}
