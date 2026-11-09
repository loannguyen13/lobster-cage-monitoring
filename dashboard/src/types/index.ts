export type EventLabel =
  | "normal" | "heat_stress" | "oxygen_deficit"
  | "algal_bloom" | "algal_crash" | "heavy_rain";

export type Reading = {
  device_id: string;
  timestamp: string;
  temperature: number;
  ph: number;
  do: number;
  salinity: number;
  turbidity: number;
  chlorophyll_a: number;
  event_label?: EventLabel;
  do_pred_15m?: number;
};

// Điểm trên biểu đồ: có thể chỉ có dự báo (chưa có số đo thật)
export type ChartPoint = Partial<Reading> & { timestamp: string };

// DO dự báo cho thời điểm target_at
export type Prediction = { target_at: string; value: number; model?: string };

export type Severity = "warning" | "critical";

export type Alert = {
  id: string;
  start: string;
  end: string; // rỗng = cảnh báo đang mở
  level: Severity;
  message: string;
  minDO: number;
  points: number;
};

export type LiveInfo = { pondId: string; pondName: string; deviceId: string };
