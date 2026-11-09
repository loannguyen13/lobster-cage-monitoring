"use client";
import type { Mode } from "@/lib/useDashboard";

export const SCENARIO_META: Record<string, string> = {
  normal: "Bình thường",
  heat_stress: "Nắng nóng",
  oxygen_deficit: "Thiếu oxy",
  algal_bloom: "Tảo nở hoa",
  algal_crash: "Sụp tảo",
  heavy_rain: "Mưa lớn",
};

// [dòng bắt đầu, số dòng] trong file CSV dataset cho từng kịch bản
const SIM_ROWS: Record<string, [number, number]> = {
  normal: [384, 145],
  heat_stress: [648, 193],
  oxygen_deficit: [840, 145],
  algal_bloom: [1224, 145],
  algal_crash: [1344, 241],
  heavy_rain: [1848, 145],
};

function simCommand(key: string): string {
  const [start, limit] = SIM_ROWS[key];
  return `python -m edge.simulator --start-row ${start} --limit ${limit} --interval 5`;
}

type Props = {
  mode: Mode; onMode: (m: Mode) => void;
  active: string | null; onSelect: (name: string) => void;
  speedMs: number; onSpeed: (ms: number) => void;
};

export default function ScenarioPanel(p: Props) {
  const cmd = p.active && SIM_ROWS[p.active] ? simCommand(p.active) : null;
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">Điều khiển kịch bản</h3>
        <div className="flex gap-2 text-sm">
          {(["replay", "live"] as const).map((m) => (
            <button key={m} onClick={() => p.onMode(m)}
              className={`rounded px-3 py-1 ${
                p.mode === m ? "bg-blue-600 text-white" : "bg-gray-100"}`}>
              {m === "replay" ? "Phát lại (offline)" : "Trực tiếp (API)"}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {Object.entries(SCENARIO_META).map(([key, label]) => (
          <button key={key} onClick={() => p.onSelect(key)}
            className={`rounded-lg border px-3 py-2 text-sm ${
              p.active === key
                ? "border-blue-600 bg-blue-50 font-medium"
                : "hover:bg-gray-50"}`}>
            {label}
          </button>
        ))}
      </div>

      {p.mode === "replay" && (
        <label className="mt-3 flex items-center gap-2 text-sm">
          Tốc độ:
          <select value={p.speedMs}
            onChange={(e) => p.onSpeed(Number(e.target.value))}
            className="rounded border px-2 py-1">
            <option value={1000}>Chậm (1 giây/điểm)</option>
            <option value={500}>Vừa (0,5 giây)</option>
            <option value={150}>Nhanh (0,15 giây)</option>
          </select>
        </label>
      )}

      {p.mode === "live" && (
        <div className="mt-3 rounded-lg bg-gray-50 p-3 text-sm text-gray-700">
          <p>
            Chế độ này hiển thị dữ liệu đang lưu trên cloud (simulator phát lại từ
            dataset mô phỏng). Bấm kịch bản không làm dữ liệu đổi ngay: muốn có dữ liệu
            theo kịch bản, chạy lệnh sau trên máy đang chạy simulator (mỗi đoạn dữ liệu
            chỉ gửi lên cloud được một lần).
          </p>
          {cmd ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="rounded bg-gray-900 px-2 py-1 text-xs text-green-300">{cmd}</code>
              <button
                className="rounded border px-2 py-1 text-xs hover:bg-white"
                onClick={() => navigator.clipboard?.writeText(cmd).catch(() => {})}
              >
                Sao chép lệnh
              </button>
            </div>
          ) : (
            <p className="mt-2 text-gray-500">Chọn một kịch bản để xem lệnh tương ứng.</p>
          )}
        </div>
      )}
    </div>
  );
}
