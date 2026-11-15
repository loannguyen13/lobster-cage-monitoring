"use client";
import { useState } from "react";
import type { Alert } from "@/types";
import { fmtTime } from "@/lib/time";

const BADGE = {
  warning: "bg-amber-100 text-amber-800",
  critical: "bg-red-100 text-red-800",
};
const SOURCE = {
  measured: { text: "Đo thực tế", style: "bg-blue-100 text-blue-800" },
  predicted: { text: "Dự báo", style: "bg-purple-100 text-purple-800" },
};
type Filter = "all" | "open" | "resolved";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Tất cả" },
  { key: "open", label: "Đang mở" },
  { key: "resolved", label: "Đã đóng" },
];

export default function AlertTable({ alerts }: { alerts: Alert[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const shown = alerts.filter((a) => filter === "all" || (filter === "open") === (a.end === ""));

  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">Lịch sử cảnh báo</h3>
        <div className="flex gap-1 text-xs">
          {FILTERS.map((f) => (
            <button key={f.key} onClick={() => setFilter(f.key)}
              className={`rounded px-2 py-1 ${filter === f.key ? "bg-blue-600 text-white" : "bg-gray-100"}`}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {shown.length === 0 ? (
        <p className="text-sm text-gray-500">Chưa có cảnh báo.</p>
      ) : (
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th>Bắt đầu</th><th>Kết thúc</th><th>Mức</th><th>Nguồn</th><th>Nội dung</th><th>DO thấp nhất</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((a) => (
                <tr key={a.id} className="border-t">
                  <td className="py-1">{fmtTime(a.start)}</td>
                  <td>{a.end ? fmtTime(a.end) : "Đang mở"}</td>
                  <td>
                    <span className={`rounded px-2 py-0.5 text-xs ${BADGE[a.level]}`}>
                      {a.level === "critical" ? "Nguy hiểm" : "Cảnh báo"}
                    </span>
                  </td>
                  <td>
                    <span className={`rounded px-2 py-0.5 text-xs ${SOURCE[a.source].style}`}>
                      {SOURCE[a.source].text}
                    </span>
                  </td>
                  <td>{a.message}</td>
                  <td>{Number.isNaN(a.minDO) ? "--" : `${a.minDO.toFixed(2)} mg/L`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
