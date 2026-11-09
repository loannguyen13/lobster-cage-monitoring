"use client";
import { useState } from "react";

export default function LoginForm({
  onLogin,
}: {
  onLogin: (username: string, password: string) => Promise<void>;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await onLogin(username.trim(), password);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Đăng nhập thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="mx-auto max-w-sm space-y-3 rounded-xl border bg-white p-6 shadow-sm"
      onSubmit={(e) => { e.preventDefault(); void submit(); }}
    >
      <h3 className="text-lg font-medium">Đăng nhập để xem dữ liệu thật</h3>
      <input
        className="w-full rounded border px-3 py-2"
        placeholder="Tên đăng nhập" autoComplete="username"
        value={username} onChange={(e) => setUsername(e.target.value)}
      />
      <input
        className="w-full rounded border px-3 py-2" type="password"
        placeholder="Mật khẩu" autoComplete="current-password"
        value={password} onChange={(e) => setPassword(e.target.value)}
      />
      {err && <p className="text-sm text-red-700">{err}</p>}
      <button
        type="submit" disabled={busy || !username || !password}
        className="w-full rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
      >
        {busy ? "Đang đăng nhập..." : "Đăng nhập"}
      </button>
    </form>
  );
}
