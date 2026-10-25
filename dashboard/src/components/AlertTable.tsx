import type { Alert } from "@/types";

const BADGE = { warning: "bg-amber-100 text-amber-800", critical: "bg-red-100 text-red-800" };
const fmt = (t: string) => t.slice(5, 16).replace("T", " ");

export default function AlertTable({ alerts }: { alerts: Alert[] }) {
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <h3 className="mb-2 font-medium">Lịch sử cảnh báo</h3>
      {alerts.length === 0 ? (
        <p className="text-sm text-gray-500">Chưa có cảnh báo.</p>
      ) : (
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th>Bắt đầu</th><th>Kết thúc</th><th>Mức</th><th>DO thấp nhất</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id} className="border-t">
                  <td className="py-1">{fmt(a.start)}</td>
                  <td>{fmt(a.end)}</td>
                  <td>
                    <span className={`rounded px-2 py-0.5 text-xs ${BADGE[a.level]}`}>
                      {a.level === "critical" ? "Nguy hiểm" : "Cảnh báo"}
                    </span>
                  </td>
                  <td>{a.minDO.toFixed(2)} mg/L</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}