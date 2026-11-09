"use client";
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { ChartPoint } from "@/types";
import { fmtTime } from "@/lib/time";

type Series = { key: string; name: string; color: string; dashed?: boolean };
type Ref = { y: number; color: string; label: string };

export default function TimeChart(props: {
  title: string; data: ChartPoint[]; series: Series[]; refs?: Ref[]; height?: number;
}) {
  const { title, data, series, refs = [], height = 260 } = props;
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <h3 className="mb-2 font-medium">{title}</h3>
      {data.length === 0 ? (
        <p className="py-10 text-center text-sm text-gray-500">Chưa có dữ liệu</p>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" tickFormatter={fmtTime} minTickGap={50} />
            <YAxis domain={["auto", "auto"]} />
            <Tooltip labelFormatter={fmtTime} />
            <Legend />
            {refs.map((r) => (
              <ReferenceLine key={r.y} y={r.y} stroke={r.color}
                strokeDasharray="4 4" label={r.label} />
            ))}
            {series.map((s) => (
              <Line key={s.key} dataKey={s.key} name={s.name} stroke={s.color}
                dot={false} strokeWidth={2} isAnimationActive={false} connectNulls
                strokeDasharray={s.dashed ? "5 5" : undefined} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
