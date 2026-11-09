// Địa chỉ API (công khai, không phải bí mật). Có thể đổi bằng NEXT_PUBLIC_API_URL.
export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ||
  "https://app-aquaculture-monitoring-api-dev-e5fegkf0fzapcedy.japanwest-01.azurewebsites.net"
).replace(/\/+$/, "");

// Chu kỳ hỏi API (ms)
export const POLL_MS = Number(process.env.NEXT_PUBLIC_POLL_MS || 5000);

export const WINDOW = 144; // số điểm giữ trên biểu đồ (chế độ Phát lại)
export const LIVE_WINDOW = 288; // số điểm giữ trên biểu đồ (chế độ Trực tiếp, 24 giờ)
export const PREFERRED_DEVICE = "LOBSTER_CAGE_VANPHONG_01";
