"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getAlertThresholds, getAlerts, getLatest, getLatestPredictions, getPredictions,
  listDevices, listPonds, loadHistory, logout as apiLogout,
} from "@/lib/api";
import { AuthError, getToken, signin } from "@/lib/auth";
import { buildAlerts, DEFAULT_THRESHOLDS } from "@/lib/alerts";
import { LIVE_WINDOW, POLL_MS, PREFERRED_DEVICE, PRIMARY_MODEL, WINDOW } from "@/lib/config";
import { mockReadings, mockScenarios } from "@/lib/mockData";
import { appendReading, forecastError, mergePredictions, ms } from "@/lib/normalize";
import type { Alert, ChartPoint, LiveInfo, Prediction, Reading, Thresholds } from "@/types";

export type Mode = "replay" | "live";
export type PredState = "loading" | "ok" | "empty" | "error";

// Chỉ dùng mô hình chính (xgboost) làm đường dự báo
const isMain = (p: Prediction) => !p.model || p.model === PRIMARY_MODEL;

export function useDashboard() {
  const [mode, setMode] = useState<Mode>("replay");
  const [scenario, setScenario] = useState<string | null>(null);
  const [speedMs, setSpeedMs] = useState(500);
  const [readings, setReadings] = useState<Reading[]>(() => mockReadings.slice(-WINDOW));
  const [preds, setPreds] = useState<Prediction[]>([]);
  const [latestPred, setLatestPred] = useState<Prediction | null>(null);
  const [predState, setPredState] = useState<PredState>("loading");
  const [predError, setPredError] = useState<string | null>(null);
  const [apiAlerts, setApiAlerts] = useState<Alert[]>([]);
  const [thresholds, setThresholds] = useState<Thresholds>(DEFAULT_THRESHOLDS);
  const [dataSource, setDataSource] = useState<string | null>(null);
  const [info, setInfo] = useState<LiveInfo | null>(null);
  const [authed, setAuthed] = useState(() => getToken() !== null);
  const [loading, setLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
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
      setLoading(false);
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

      // Ngưỡng cảnh báo đọc từ luật của hệ thống (không viết cứng)
      getAlertThresholds(pond.id)
        .then((t) => { if (alive && t) setThresholds(t); })
        .catch(() => {});

      // Mốc thời gian của số liệu mới nhất, làm tâm khoảng thời gian lấy dự báo
      let anchor: string | undefined;

      // Cảnh báo và dự báo: mỗi phần có trạng thái riêng, lỗi một phần không làm hỏng phần khác
      const refreshExtras = async () => {
        const range = anchor
          ? {
              from: new Date(ms(anchor) - LIVE_WINDOW * 5 * 60000).toISOString(),
              to: new Date(ms(anchor) + 3600000).toISOString(),
            }
          : undefined;
        const [al, pr, lp] = await Promise.allSettled([
          getAlerts(pond.id),
          // mỗi số đo có 2 dòng dự báo (xgboost, persistence) nên lấy gấp đôi
          getPredictions(deviceId, LIVE_WINDOW * 2, range),
          getLatestPredictions(deviceId),
        ]);
        if (!alive) return;
        if (al.status === "fulfilled") setApiAlerts(al.value);
        else if (al.reason instanceof AuthError) { handle(al.reason); return; }
        if (pr.status === "rejected" && pr.reason instanceof AuthError) { handle(pr.reason); return; }
        if (lp.status === "fulfilled" && lp.value.dataSource) setDataSource(lp.value.dataSource);

        if (pr.status === "rejected" && lp.status === "rejected") {
          setPredState("error");
          setPredError(pr.reason instanceof Error ? pr.reason.message : "Không tải được dự báo");
          return;
        }
        const list = pr.status === "fulfilled" ? pr.value.filter(isMain) : [];
        const latestList = lp.status === "fulfilled" ? lp.value.items.filter(isMain) : [];
        const newest =
          latestList[0] ?? [...list].sort((a, b) => ms(b.target_at) - ms(a.target_at))[0] ?? null;
        setPreds(list);
        setLatestPred(newest);
        setPredState(list.length === 0 && !newest ? "empty" : "ok");
        setPredError(null);
      };

      // Lịch sử gần nhất (có from/to, xem loadHistory)
      const { history, latest } = await loadHistory(pond.id, deviceId, LIVE_WINDOW);
      if (!alive) return;
      anchor = history.length > 0 ? history[history.length - 1].timestamp : latest?.timestamp;
      setReadings(history);
      setError(null);
      setLoading(false);
      await refreshExtras();

      let tick = 0;
      timer = setInterval(async () => {
        try {
          const r = await getLatest(pond.id, deviceId);
          if (!alive || !r) return;
          anchor = r.timestamp;
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
  }, [mode, authed, reloadKey]);

  const resetLive = useCallback(() => {
    setPreds([]);
    setLatestPred(null);
    setPredState("loading");
    setPredError(null);
    setApiAlerts([]);
    setThresholds(DEFAULT_THRESHOLDS);
    setDataSource(null);
    setInfo(null);
  }, []);

  const changeMode = useCallback((m: Mode) => {
    if (m === mode) return; // bấm lại đúng chế độ đang dùng thì bỏ qua
    setMode(m);
    setScenario(null);
    setError(null);
    cursor.current = 0;
    resetLive();
    setLoading(m === "live" && getToken() !== null);
    setReadings(m === "replay" ? mockReadings.slice(-WINDOW) : []);
  }, [mode, resetLive]);

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
    setLoading(true);
    setPredState("loading");
    setAuthed(true);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setAuthed(false);
    setLoading(false);
    setReadings([]);
    resetLive();
  }, [resetLive]);

  // Thử lại khi tải dữ liệu bị lỗi
  const reload = useCallback(() => {
    setError(null);
    setLoading(true);
    setPredState("loading");
    setReloadKey((k) => k + 1);
  }, []);

  // ---------- Dữ liệu dẫn xuất ----------
  const chartData: ChartPoint[] = useMemo(
    () => (mode === "live" ? mergePredictions(readings, preds) : readings),
    [mode, readings, preds]
  );

  // Dự báo mới nhất hiển thị ở thẻ dự báo (chế độ Phát lại dùng dữ liệu mô phỏng)
  const forecast: Prediction | null = useMemo(() => {
    if (mode === "live") return latestPred;
    for (let i = readings.length - 1; i >= 0; i--) {
      const r = readings[i];
      if (r.do_pred_15m !== undefined) {
        return { target_at: r.timestamp, value: r.do_pred_15m, model: "mô phỏng", horizon_minutes: 15 };
      }
    }
    return null;
  }, [mode, latestPred, readings]);

  const forecastState: PredState = mode === "live" ? predState : forecast ? "ok" : "empty";
  const stats = useMemo(() => forecastError(chartData), [chartData]);

  // Cảnh báo: chế độ Trực tiếp ưu tiên cảnh báo do backend tạo; nếu chưa có thì tự tính từ số đo.
  // Chế độ Phát lại tính cả cảnh báo từ số đo và cảnh báo từ dự báo (mô phỏng).
  const alerts = useMemo(() => {
    const measured = buildAlerts(
      readings.map((r) => ({ timestamp: r.timestamp, value: r.do })), thresholds, "measured"
    );
    if (mode === "live") return apiAlerts.length > 0 ? apiAlerts : measured;
    const predicted = buildAlerts(
      readings
        .filter((r) => r.do_pred_15m !== undefined)
        .map((r) => ({ timestamp: r.timestamp, value: r.do_pred_15m as number })),
      thresholds, "predicted"
    );
    return [...measured, ...predicted].sort((a, b) => ms(b.start) - ms(a.start));
  }, [mode, readings, apiAlerts, thresholds]);

  return {
    mode, changeMode, scenario, selectScenario, speedMs, setSpeedMs,
    readings, chartData, alerts, thresholds, forecast, forecastState, predError, stats,
    dataSource, info, authed, login, logout, loading, reload, error,
  };
}
