export type EventLabel =
  | "normal" | "heat_stress" | "oxygen_deficit"
  | "algal_bloom" | "algal_crash" | "heavy_rain";

export type Reading = {
  device_id: string;
  timestamp: string;        // "2026-10-05T10:00:00"
  temperature: number;      // °C
  ph: number;
  do: number;               // mg/L
  salinity: number;         // ppt
  turbidity: number;        // NTU
  chlorophyll_a: number;    // µg/L
  event_label?: EventLabel; // có thể không có khi chạy thật
  do_pred_15m?: number;     // DO dự báo 15 phút tới (mock)
};

export type Severity = "warning" | "critical";

export type Alert = {
  id: string;
  start: string;
  end: string;
  level: Severity;
  message: string;
  minDO: number;
  points: number;
};