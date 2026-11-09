"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getAlerts, getLatest, getPredictions, listDevices, listPonds,
  loadHistory, logout as apiLogout,
} from "@/lib/api";
import { AuthError, getToken, signin } from "@/lib/auth";
import { LIVE_WINDOW, POLL_MS, PREFERRED_DEVICE, WINDOW } from "@/lib/config";
import { mockReadings, mockScenarios } from "@/lib/mockData";
import { appendReading, mergePredictions } from "@/lib/normalize";
import type { Alert, ChartPoint, LiveInfo, Prediction, Reading } from "@/types";

export type Mode = "replay" | "live";

export function useDashboard() {
  const [mode, setMode] = useState<Mode>("replay");
  const [scenario, setScenario] = useState<string | null>(null);
  const [speedMs, setSpeedMs] = useState(500);
  const [readings, setReadings] = useState<Reading[]>(() => mockReadings.slice(-WINDOW));
  const [preds, setPreds] = useState<Prediction[]>([]);
  const [apiAlerts, setApiAlerts] = useState<Alert[]>([]);
  const [info, setInfo] = useState<LiveInfo | null>(null);
  const [authed, setAuthed] = useState(() => getToken() !== null);
  const [error, setError] = useState<string | null>(null);
  const cursor = useRef(0); // vị trí đang phát trong kịch bản (chế độ Phát lại)

  // ---------- Chế độ Phát lại (offline): phát từng điểm của kịch bản mẫu ----------
  useEffect(() => {
    if (mode !== "replay" || !scenario) return;
    const data = mockScenarios[scenario];
    const id = setInterval(() => {
      const i = cursor.current;
      if (i >= data.length) return;
      cursor.current = i + 1;
      setReadings((prev) => [...prev, data[i]].slice(-WINDOW));
    }, speedMs);
    return () => clearInterval(id);
  }, [mode, scenario, speedMs]);

  // ---------- Chế độ Trực tiếp: đọc dữ liệu thật từ API ----------
  useEffect(() => {
    if (mode !== "live" || !authed) return;
    let alive = true;
    let timer: ReturnType<typeof setInterval> | undefined;

    const handle = (e: unknown) => {
      if (!alive) return;
      if (e instanceof AuthError) setAuthed(false);
      setError(e instanceof Error ? e.message : "Lỗi không xác định");
    };

    const start = async () => {
      const ponds = await listPonds();
      if (ponds.length === 0) throw new Error("Tài khoản này chưa có ao nào");
      const pond = ponds[0];
      const devices = await listDevices(pond.id);
      const deviceId = devices.includes(PREFERRED_DEVICE) ? PREFERRED_DEVICE : devices[0];
      if (!deviceId) throw new Error("Ao này chưa có thiết bị nào");
      if (!alive) return;
      setInfo({ pondId: pond.id, pondName: pond.name, deviceId });

      // Cảnh báo và dự báo (một trong hai lỗi thì phần còn lại vẫn chạy)
      const refreshExtras = async () => {
        const [al, pr] = await Promise.allSettled([
          getAlerts(pond.id),
          getPredictions(deviceId, LIVE_WINDOW),
        ]);
        if (!alive) return;
        if (al.status === "fulfilled") setApiAlerts(al.value);
        else if (al.reason instanceof AuthError) handle(al.reason);
        if (pr.status === "fulfilled") setPreds(pr.value);
        else if (pr.reason instanceof AuthError) handle(pr.reason);
      };

      // Lịch sử gần nhất (có from/to, xem loadHistory)
      const { history } = await loadHistory(pond.id, deviceId, LIVE_WINDOW);
      if (!alive) return;
      setReadings(history);
      setError(null);
      await refreshExtras();

      let tick = 0;
      timer = setInterval(async () => {
        try {
          const r = await getLatest(pond.id, deviceId);
          if (!alive || !r) return;
          setError(null);
          setReadings((prev) => appendReading(prev, r, LIVE_WINDOW));
          tick += 1;
          if (tick % 4 === 0) void refreshExtras();
        } catch (e) {
          handle(e);
        }
      }, POLL_MS);
    };

    start().catch(handle);
    return () => {
      alive = false;
      if (timer) clearInterval(timer);
    };
  }, [mode, authed]);

  const changeMode = useCallback((m: Mode) => {
    setMode(m);
    setScenario(null);
    setError(null);
    cursor.current = 0;
    setPreds([]);
    setApiAlerts([]);
    setInfo(null);
    setReadings(m === "replay" ? mockReadings.slice(-WINDOW) : []);
  }, []);

  const selectScenario = useCallback(
    (name: string) => {
      setScenario(name);
      if (mode === "replay") {
        cursor.current = 0;
        setReadings([]); // xóa biểu đồ rồi phát từ đầu
      }
      // Chế độ Trực tiếp: chỉ hiển thị lệnh simulator tương ứng (xem ScenarioPanel)
    },
    [mode]
  );

  const login = useCallback(async (username: string, password: string) => {
    await signin(username, password);
    setError(null);
    setAuthed(true);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setAuthed(false);
    setReadings([]);
    setPreds([]);
    setApiAlerts([]);
    setInfo(null);
  }, []);

  const chartData: ChartPoint[] = useMemo(
    () => (mode === "live" ? mergePredictions(readings, preds) : readings),
    [mode, readings, preds]
  );

  return {
    mode, changeMode, scenario, selectScenario, speedMs, setSpeedMs,
    readings, chartData, apiAlerts, info, authed, login, logout, error,
  };
}
