type Props = {
  label: string; value?: number; unit: string;
  status?: "ok" | "warning" | "critical"; digits?: number;
};
const STYLE = {
  ok: "border-emerald-300 bg-emerald-50",
  warning: "border-amber-300 bg-amber-50",
  critical: "border-red-300 bg-red-50",
};

export default function MetricCard({ label, value, unit, status = "ok", digits = 2 }: Props) {
  return (
    <div className={`rounded-xl border p-4 shadow-sm ${STYLE[status]}`}>
      <p className="text-sm text-gray-600">{label}</p>
      <p className="mt-1 text-3xl font-semibold text-gray-900">
        {value === undefined ? "--" : value.toFixed(digits)}{" "}
        <span className="text-base font-normal text-gray-500">{unit}</span>
      </p>
    </div>
  );
}