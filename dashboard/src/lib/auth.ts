import { API_BASE } from "@/lib/config";

const KEY = "lobster_token";
let memory: string | null = null;

export class AuthError extends Error {}

export function getToken(): string | null {
  if (memory) return memory;
  try {
    memory = typeof window !== "undefined" ? window.sessionStorage.getItem(KEY) : null;
  } catch {
    memory = null;
  }
  return memory;
}

export function setToken(token: string | null) {
  memory = token;
  try {
    if (typeof window === "undefined") return;
    if (token) window.sessionStorage.setItem(KEY, token);
    else window.sessionStorage.removeItem(KEY);
  } catch {
    /* bỏ qua nếu trình duyệt chặn lưu trữ */
  }
}

export function findToken(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const o = body as Record<string, unknown>;
  for (const k of ["access_token", "token", "accessToken", "jwt"]) {
    const v = o[k];
    if (typeof v === "string" && v) return v;
  }
  for (const v of Object.values(o)) {
    if (v && typeof v === "object") {
      const t = findToken(v);
      if (t) return t;
    }
  }
  return null;
}

// Đăng nhập; trả về nội dung phản hồi (dùng cho trang /debug)
export async function signin(username: string, password: string): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/auth/signin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    throw new Error("Không kết nối được API (kiểm tra mạng hoặc cấu hình CORS)");
  }
  if ([400, 401, 403, 422].includes(res.status)) {
    throw new AuthError("Sai tên đăng nhập hoặc mật khẩu");
  }
  if (!res.ok) throw new Error(`Đăng nhập thất bại (mã ${res.status})`);
  const body: unknown = await res.json();
  const token = findToken(body);
  if (!token) throw new Error("API không trả về access_token");
  setToken(token);
  return body;
}
