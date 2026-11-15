"use client";
import MetricCard from "@/components/MetricCard";
import TimeChart from "@/components/TimeChart";
import AlertTable from "@/components/AlertTable";
import ScenarioPanel from "@/components/ScenarioPanel";
import LoginForm from "@/components/LoginForm";
import ForecastCard from "@/components/ForecastCard";
import { useDashboard } from "@/lib/useDashboard";
import { levelOf } from "@/lib/alerts";
import { METRICS } from "@/lib/metrics";
import type { Reading } from "@/types";

export default function Page() {
  const d = useDashboard();
  const live = d.mode === "live";
  const latest: Reading | undefined = d.readings[d.readings.length - 1];
  const doStatus = latest ? levelOf(latest.do, d.thresholds) ?? "ok" : "ok";
  const horizon = d.forecast?.horizon_minutes ?? 15;

  // Chỉ hiện đường dự báo khi thật sự có dữ liệu dự báo
  const hasPred = d.chartData.some((p) => p.do_pred_15m !== undefined);
  const doSeries = [
    { key: "do", name: "DO thực tế", color: "#2563eb" },
    ...(hasPred
      ? [{
          key: "do_pred_15m",
          name: live ? `DO dự báo +${horizon} phút (XGBoost)` : `DO dự báo +${horizon} phút (mô phỏng)`,
          color: "#f97316",
          dashed: true,
        }]
      : []),
  ];

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">
          Giám sát chất lượng nước – Lồng tôm hùm Khánh Hòa
        </h1>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="rounded-full bg-gray-100 px-3 py-1">
            {live
              ? `${d.info?.pondName ?? "—"} · ${d.info?.deviceId ?? "—"}`
              : `Sự kiện: ${latest?.event_label ?? "—"}`}
          </span>
          <span className="rounded-full bg-gray-100 px-3 py-1">
            Dữ liệu: {live ? d.dataSource ?? "—" : "mẫu mô phỏng"}
          </span>
          {live && d.authed && (
            <button className="rounded border px-3 py-1 hover:bg-gray-50"
              onClick={() => void d.logout()}>
              Đăng xuất
            </button>
          )}
        </div>
      </header>

      <ScenarioPanel
        mode={d.mode} onMode={d.changeMode}
        active={d.scenario} onSelect={d.selectScenario}
        speedMs={d.speedMs} onSpeed={d.setSpeedMs}
      />

      {d.error && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          <span>{d.error}</span>
          {live && d.authed && (
            <button className="rounded border border-red-300 px-3 py-1 hover:bg-red-100" onClick={d.reload}>
              Thử lại
            </button>
          )}
        </div>
      )}

      {live && !d.authed ? (
        <LoginForm onLogin={d.login} />
      ) : (
        <>
          {live && d.loading && (
            <p className="rounded-lg bg-blue-50 p-3 text-sm text-blue-800">Đang tải dữ liệu từ API...</p>
          )}

          <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {METRICS.map((m) => (
              <MetricCard key={m.key} label={m.label} unit={m.unit}
                value={latest?.[m.key]}
                status={m.key === "do" ? doStatus : "ok"} />
            ))}
          </section>

          <div className="grid gap-4 lg:grid-cols-4">
            <div className="lg:col-span-3">
              <TimeChart
                title="DO thực tế và dự báo (mg/L)"
                data={d.chartData}
                series={doSeries}
                refs={[
                  { y: d.thresholds.warning, color: "#d97706", label: String(d.thresholds.warning) },
                  { y: d.thresholds.critical, color: "#dc2626", label: String(d.thresholds.critical) },
                ]}
              />
            </div>
            <ForecastCard
              state={d.forecastState} pred={d.forecast} thresholds={d.thresholds}
              error={d.predError} onRetry={d.reload} stats={d.stats}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <TimeChart
              title="Nhiệt độ (°C)"
              data={d.chartData}
              height={220}
              series={[{ key: "temperature", name: "Nhiệt độ (°C)", color: "#ef4444" }]}
            />
            <TimeChart
              title="pH"
              data={d.chartData}
              height={220}
              series={[{ key: "ph", name: "pH", color: "#8b5cf6" }]}
            />
            <TimeChart
              title="Độ mặn (ppt)"
              data={d.chartData}
              height={220}
              series={[{ key: "salinity", name: "Độ mặn (ppt)", color: "#0891b2" }]}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <TimeChart
              title="Chlorophyll-a và độ đục"
              data={d.chartData}
              series={[
                { key: "chlorophyll_a", name: "Chlorophyll-a (µg/L)", color: "#16a34a" },
                { key: "turbidity", name: "Độ đục (NTU)", color: "#6b7280" },
              ]}
            />
            <AlertTable alerts={d.alerts} />
          </div>
        </>
      )}
    </main>
  );
}
