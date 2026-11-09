"use client";
import { useMemo } from "react";
import MetricCard from "@/components/MetricCard";
import TimeChart from "@/components/TimeChart";
import AlertTable from "@/components/AlertTable";
import ScenarioPanel from "@/components/ScenarioPanel";
import LoginForm from "@/components/LoginForm";
import { useDashboard } from "@/lib/useDashboard";
import { buildAlerts, levelOf } from "@/lib/alerts";
import { METRICS } from "@/lib/metrics";
import type { Reading } from "@/types";

export default function Page() {
  const d = useDashboard();
  const live = d.mode === "live";
  const latest: Reading | undefined = d.readings[d.readings.length - 1];
  const doStatus = latest ? levelOf(latest.do) ?? "ok" : "ok";
  const alerts = useMemo(
    () => (live && d.apiAlerts.length > 0 ? d.apiAlerts : buildAlerts(d.readings)),
    [live, d.apiAlerts, d.readings]
  );

  // Chỉ hiện đường dự báo khi thật sự có dữ liệu dự báo
  const hasPred = d.chartData.some((p) => p.do_pred_15m !== undefined);
  const doSeries = [
    { key: "do", name: "DO thực tế", color: "#2563eb" },
    ...(hasPred
      ? [{
          key: "do_pred_15m",
          name: live ? "DO dự báo +15'" : "DO dự báo +15' (mô phỏng)",
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
        <div className="flex items-center gap-2 text-sm">
          <span className="rounded-full bg-gray-100 px-3 py-1">
            {live
              ? `${d.info?.pondName ?? "—"} · ${d.info?.deviceId ?? "—"}`
              : `Sự kiện: ${latest?.event_label ?? "—"}`}
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
        <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{d.error}</p>
      )}

      {live && !d.authed ? (
        <LoginForm onLogin={d.login} />
      ) : (
        <>
          <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {METRICS.map((m) => (
              <MetricCard key={m.key} label={m.label} unit={m.unit}
                value={latest?.[m.key]}
                status={m.key === "do" ? doStatus : "ok"} />
            ))}
          </section>

          <TimeChart
            title="DO thực tế và dự báo 15 phút (mg/L)"
            data={d.chartData}
            series={doSeries}
            refs={[
              { y: 4, color: "#d97706", label: "4.0" },
              { y: 3, color: "#dc2626", label: "3.0" },
            ]}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <TimeChart
              title="Chlorophyll-a và độ đục"
              data={d.chartData}
              series={[
                { key: "chlorophyll_a", name: "Chlorophyll-a (µg/L)", color: "#16a34a" },
                { key: "turbidity", name: "Độ đục (NTU)", color: "#6b7280" },
              ]}
            />
            <AlertTable alerts={alerts} />
          </div>
        </>
      )}
    </main>
  );
}
