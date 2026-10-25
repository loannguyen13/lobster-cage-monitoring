"use client";
import { useMemo } from "react";
import MetricCard from "@/components/MetricCard";
import TimeChart from "@/components/TimeChart";
import AlertTable from "@/components/AlertTable";
import ScenarioPanel from "@/components/ScenarioPanel";
import { mockReadings } from "@/lib/mockData";
import { buildAlerts, levelOf } from "@/lib/alerts";
import { METRICS } from "@/lib/metrics";

export default function Page() {
  const readings = mockReadings;
  const latest = readings[readings.length - 1];
  const alerts = useMemo(() => buildAlerts(readings), [readings]);

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">
          Giám sát chất lượng nước – Lồng tôm hùm Khánh Hòa
        </h1>
        <span className="rounded-full bg-gray-100 px-3 py-1 text-sm">
          Sự kiện: {latest.event_label ?? "—"}
        </span>
      </header>

      <ScenarioPanel />

      <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {METRICS.map((m) => (
          <MetricCard key={m.key} label={m.label} unit={m.unit} value={latest[m.key]}
            status={m.key === "do" ? levelOf(latest.do) ?? "ok" : "ok"} />
        ))}
      </section>

      <TimeChart
        title="DO thực tế và dự báo 15 phút (mg/L)"
        data={readings}
        series={[
          { key: "do", name: "DO thực tế", color: "#2563eb" },
          { key: "do_pred_15m", name: "DO dự báo +15'", color: "#f97316", dashed: true },
        ]}
        refs={[
          { y: 4, color: "#d97706", label: "4.0" },
          { y: 3, color: "#dc2626", label: "3.0" },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <TimeChart
          title="Chlorophyll-a và độ đục"
          data={readings}
          series={[
            { key: "chlorophyll_a", name: "Chlorophyll-a (µg/L)", color: "#16a34a" },
            { key: "turbidity", name: "Độ đục (NTU)", color: "#6b7280" },
          ]}
        />
        <AlertTable alerts={alerts} />
      </div>
    </main>
  );
}