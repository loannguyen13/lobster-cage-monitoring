import { levelOf } from "@/lib/alerts";
import { fmtTime } from "@/lib/time";
import type { PredState } from "@/lib/useDashboard";
import type { Prediction, Thresholds } from "@/types";

const TONE = {
  ok: "border-emerald-300 bg-emerald-50",
  warning: "border-amber-300 bg-amber-50",
  critical: "border-red-300 bg-red-50",
};

type Props = {
  state: PredState;
  pred: Prediction | null;
  thresholds: Thresholds;
  error: string | null;
  onRetry: () => void;
  stats: { mae: number; rmse: number; n: number } | null;
};

export default function ForecastCard({ state, pred, thresholds, error, onRetry, stats }: Props) {
  const horizon = pred?.horizon_minutes ?? 15;
  const level = pred ? levelOf(pred.value, thresholds) ?? "ok" : "ok";
  return (
    <div className={`rounded-xl border p-4 shadow-sm ${state === "ok" ? TONE[level] : "bg-white"}`}>
      <h3 className="font-medium">DO dự báo +{horizon} phút</h3>

      {state === "loading" && <p className="mt-3 text-sm text-gray-500">Đang tải dự báo...</p>}

      {state === "empty" && (
        <p className="mt-3 text-sm text-gray-500">
          Chưa có dự báo cho thiết bị này. Backend chưa ghi dữ liệu dự báo.
        </p>
      )}

      {state === "error" && (
        <div className="mt-3 space-y-2 text-sm">
          <p className="text-red-700">{error ?? "Không tải được dự báo."}</p>
          <button className="rounded border px-3 py-1 hover:bg-gray-50" onClick={onRetry}>
            Thử lại
          </button>
        </div>
      )}

      {state === "ok" && pred && (
        <div className="mt-2 space-y-1 text-sm text-gray-700">
          <p className="text-3xl font-semibold text-gray-900">
            {pred.value.toFixed(2)} <span className="text-base font-normal text-gray-500">mg/L</span>
          </p>
          <p>Dự báo cho thời điểm {fmtTime(pred.target_at)}</p>
          {pred.generated_at && <p>Tạo lúc {fmtTime(pred.generated_at)}</p>}
          <p>Mô hình: {pred.model ?? "—"}</p>
          {level !== "ok" && (
            <p className="font-medium">
              {level === "critical" ? "Dự báo dưới ngưỡng nguy hiểm" : "Dự báo dưới ngưỡng cảnh báo"}
            </p>
          )}
          {stats && (
            <p className="border-t pt-1 text-xs text-gray-600">
              Sai số trong cửa sổ: MAE {stats.mae.toFixed(2)}, RMSE {stats.rmse.toFixed(2)} ({stats.n} cặp)
            </p>
          )}
        </div>
      )}
    </div>
  );
}
