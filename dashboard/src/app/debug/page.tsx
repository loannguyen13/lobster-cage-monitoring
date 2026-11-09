"use client";
import { useState } from "react";
import { signin } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { asList, pick } from "@/lib/normalize";
import { PREFERRED_DEVICE } from "@/lib/config";

const SECRET = /token|password|secret|authorization/i;

// Che token / mật khẩu trước khi hiển thị
function redact(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(redact);
  if (v && typeof v === "object") {
    return Object.fromEntries(
      Object.entries(v as Record<string, unknown>).map(([k, x]) => [k, SECRET.test(k) ? "xxx" : redact(x)])
    );
  }
  return v;
}

// Chỉ giữ 2 phần tử đầu của mỗi danh sách cho gọn
function short(v: unknown): unknown {
  if (Array.isArray(v)) return { so_phan_tu: v.length, hai_phan_tu_dau: v.slice(0, 2) };
  if (v && typeof v === "object") {
    return Object.fromEntries(
      Object.entries(v as Record<string, unknown>).map(([k, x]) =>
        [k, Array.isArray(x) ? { so_phan_tu: x.length, hai_phan_tu_dau: x.slice(0, 2) } : x]
      )
    );
  }
  return v;
}

export default function DebugPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setOut("Đang chạy...");
    const parts: string[] = [];
    const add = (title: string, data: unknown) =>
      parts.push(`### ${title}\n${JSON.stringify(redact(short(data)), null, 1)}`);
    const step = async (title: string, path: string): Promise<unknown> => {
      try {
        const data = await apiFetch(path);
        add(title, data);
        return data;
      } catch (e) {
        parts.push(`### ${title}\nLỖI: ${e instanceof Error ? e.message : String(e)}`);
        return undefined;
      }
    };

    try {
      add("POST /api/auth/signin", await signin(username.trim(), password));
    } catch (e) {
      setOut(`Đăng nhập lỗi: ${e instanceof Error ? e.message : String(e)}`);
      setBusy(false);
      return;
    }

    await step("GET /api/auth/me", "/api/auth/me");
    const ponds = await step("GET /api/ponds", "/api/ponds");
    const pondId = String(pick(asList(ponds)[0] ?? {}, "id", "pond_id") ?? "1");
    const devices = await step(`GET /api/devices?pond_id=${pondId}`, `/api/devices?pond_id=${pondId}`);
    const ids = asList(devices).map((r) => String(pick(r, "device_id", "id") ?? "")).filter(Boolean);
    const deviceId = ids.includes(PREFERRED_DEVICE) ? PREFERRED_DEVICE : ids[0] ?? PREFERRED_DEVICE;

    const latestData = await step("GET /api/readings/latest", `/api/readings/latest?pond_id=${pondId}`);
    await step("GET /api/readings (limit=3, không from/to)", `/api/readings?device_id=${deviceId}&limit=3`);
    const ts = pick(asList(latestData)[0] ?? {}, "timestamp");
    if (typeof ts === "string" && !Number.isNaN(Date.parse(ts))) {
      const to = Date.parse(ts);
      const q = new URLSearchParams({
        device_id: deviceId,
        from: new Date(to - 24 * 3600000).toISOString(),
        to: new Date(to + 60000).toISOString(),
        limit: "3",
      });
      await step("GET /api/readings (limit=3, CÓ from/to quanh bản ghi mới nhất)", `/api/readings?${q.toString()}`);
    }
    await step("GET /api/dashboard", `/api/dashboard?pond_id=${pondId}`);
    await step("GET /api/alerts (limit=3)", `/api/alerts?pond_id=${pondId}&limit=3`);
    await step("GET /api/alert-rules", `/api/alert-rules?pond_id=${pondId}`);
    await step("GET /api/predictions/latest", `/api/predictions/latest?device_id=${deviceId}`);
    await step("GET /api/predictions (limit=3)", `/api/predictions?device_id=${deviceId}&limit=3`);

    setOut(parts.join("\n\n"));
    setBusy(false);
  }

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-xl font-semibold">Kiểm tra API (trang gỡ lỗi)</h1>
      <p className="text-sm text-gray-600">
        Đăng nhập rồi bấm Chạy thử. Kết quả đã tự che token và mật khẩu, có thể
        sao chép gửi cho người hỗ trợ.
      </p>
      <input className="w-full rounded border px-3 py-2" placeholder="Tên đăng nhập"
        value={username} onChange={(e) => setUsername(e.target.value)} />
      <input className="w-full rounded border px-3 py-2" type="password" placeholder="Mật khẩu"
        value={password} onChange={(e) => setPassword(e.target.value)} />
      <div className="flex gap-2">
        <button className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          disabled={busy || !username || !password} onClick={() => void run()}>
          {busy ? "Đang chạy..." : "Chạy thử tất cả endpoint"}
        </button>
        <button className="rounded border px-4 py-2" disabled={!out}
          onClick={() => navigator.clipboard?.writeText(out).catch(() => {})}>
          Sao chép kết quả
        </button>
      </div>
      <textarea readOnly value={out} rows={30}
        className="w-full rounded border bg-gray-50 p-3 font-mono text-xs" />
    </main>
  );
}
