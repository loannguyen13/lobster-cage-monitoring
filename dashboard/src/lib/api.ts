import { API_BASE } from "@/lib/config";
import { AuthError, getToken, setToken } from "@/lib/auth";
import { asList, ms, pick, sortAsc, toAlert, toPrediction, toReading } from "@/lib/normalize";
import type { Alert, Prediction, Reading } from "@/types";

export async function apiFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new Error("Không kết nối được API (kiểm tra mạng hoặc cấu hình CORS)");
  }
  if (res.status === 401) {
    setToken(null);
    throw new AuthError("Phiên đăng nhập đã hết hạn, hãy đăng nhập lại");
  }
  if (!res.ok) throw new Error(`API lỗi ${res.status}: ${path}`);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export type Pond = { id: string; name: string };

export async function listPonds(): Promise<Pond[]> {
  const rows = asList(await apiFetch("/api/ponds"));
  return rows
    .map((r) => ({
      id: String(pick(r, "id", "pond_id") ?? ""),
      name: String(pick(r, "name", "pond_name") ?? "Ao"),
    }))
    .filter((p) => p.id !== "");
}

export async function listDevices(pondId: string): Promise<string[]> {
  const rows = asList(await apiFetch(`/api/devices?pond_id=${encodeURIComponent(pondId)}`));
  return rows.map((r) => String(pick(r, "device_id", "id") ?? "")).filter(Boolean);
}

export async function getLatest(pondId: string, deviceId: string): Promise<Reading | undefined> {
  const rows = asList(await apiFetch(`/api/readings/latest?pond_id=${encodeURIComponent(pondId)}`))
    .map(toReading)
    .filter((r): r is Reading => r !== null);
  return rows.find((r) => r.device_id === deviceId) ?? rows[0];
}

export async function getHistory(
  deviceId: string,
  opts: { limit?: number; from?: string; to?: string } = {}
): Promise<Reading[]> {
  const q = new URLSearchParams({ device_id: deviceId, limit: String(opts.limit ?? 144) });
  if (opts.from) q.set("from", opts.from);
  if (opts.to) q.set("to", opts.to);
  return asList(await apiFetch(`/api/readings?${q.toString()}`))
    .map(toReading)
    .filter((r): r is Reading => r !== null);
}

// Lịch sử gần nhất, tính lùi từ bản ghi mới nhất.
// API /api/readings trả danh sách RỖNG nếu không truyền from/to (mặc định chỉ lấy
// khoảng thời gian gần "bây giờ"), nên luôn truyền from/to quanh bản ghi mới nhất.
export async function loadHistory(
  pondId: string,
  deviceId: string,
  size: number
): Promise<{ history: Reading[]; latest?: Reading }> {
  const latest = await getLatest(pondId, deviceId);
  let history: Reading[] = [];
  if (latest) {
    const to = ms(latest.timestamp);
    history = sortAsc(
      await getHistory(deviceId, {
        from: new Date(to - size * 5 * 60000).toISOString(),
        to: new Date(to + 60000).toISOString(),
        limit: size + 10,
      })
    );
  }
  if (history.length === 0) history = sortAsc(await getHistory(deviceId, { limit: size }));
  if (history.length === 0 && latest) history = [latest];
  return { history: history.slice(-size), latest };
}

export async function getAlerts(pondId: string): Promise<Alert[]> {
  const q = new URLSearchParams({ pond_id: pondId, limit: "100" });
  return asList(await apiFetch(`/api/alerts?${q.toString()}`)).map((r, i) => toAlert(r, i));
}

export async function getPredictions(deviceId: string, limit = 144): Promise<Prediction[]> {
  const q = new URLSearchParams({ device_id: deviceId, limit: String(limit) });
  return asList(await apiFetch(`/api/predictions?${q.toString()}`))
    .map(toPrediction)
    .filter((p): p is Prediction => p !== null);
}

export async function logout() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch {
    /* vẫn xóa phiên ở phía trình duyệt */
  }
  setToken(null);
}
