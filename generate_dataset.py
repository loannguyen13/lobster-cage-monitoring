
import numpy as np
import pandas as pd

# ==========================================
# 1. CẤU HÌNH THỜI GIAN & THIẾT BỊ
# ==========================================
start_date = "2026-10-01 00:00:00"
periods = 7 * 24 * 12  # 2016 bản ghi, mỗi 5 phút
timestamps = pd.date_range(
    start=start_date,
    periods=periods,
    freq="5min"
)

np.random.seed(42)
n = len(timestamps)

hours = np.asarray(
    timestamps.hour + timestamps.minute / 60.0,
    dtype=float
)
indices = np.arange(n)

# ==========================================
# 2. SINH DỮ LIỆU NỀN
# ==========================================
temp_base = np.asarray(
    28.0 + 1.8 * np.sin(2 * np.pi * (hours - 8) / 24),
    dtype=float
)
do_base = np.asarray(
    5.8 + 1.6 * np.sin(2 * np.pi * (hours - 9) / 24),
    dtype=float
)
ph_base = np.asarray(
    8.1 + 0.3 * np.sin(2 * np.pi * (hours - 9) / 24),
    dtype=float
)

salinity_base = np.full(n, 32.0, dtype=float)
turbidity_base = np.full(n, 8.0, dtype=float)

# Chlorophyll-a nền (đơn vị mô phỏng: µg/L)
chlorophyll_base = np.full(n, 5.0, dtype=float)

# ==========================================
# 3. CÁC KỊCH BẢN SINH THÁI
# ==========================================

# Kịch bản 1: DO giảm từ 1h đến 6h mỗi đêm
night_mask = (hours >= 1.0) & (hours <= 6.0)
do_base[night_mask] -= (
    1.5 * np.sin(
        np.pi * (hours[night_mask] - 1.0) / 5.0
    )
)

# Kịch bản 2: Nắng nóng ngày thứ 3
day3_mask = (indices >= 2 * 288) & (indices < 3 * 288)
temp_base[day3_mask] += 3.2

heat_impact = np.maximum(0, temp_base - 31.5) ** 1.4
do_base -= 0.6 * heat_impact

# Kịch bản 3: Khủng hoảng DO trong 7 giờ đầu ngày thứ 4
day4_night_start = 3 * 288
day4_night_end = day4_night_start + 84
benthic_crisis_idx = slice(day4_night_start, day4_night_end)

do_base[benthic_crisis_idx] -= 2.2
ph_base[benthic_crisis_idx] -= 0.45

# Kịch bản 4A: Tảo nở hoa ngày thứ 5, 10h–16h
bloom_start = 4 * 288 + 120
bloom_end = 4 * 288 + 192
bloom_idx = slice(bloom_start, bloom_end)

ph_base[bloom_idx] += 0.75
do_base[bloom_idx] += 2.2
turbidity_base[bloom_idx] += 12.0

chlorophyll_base[bloom_idx] = np.linspace(
    25.0, 50.0, bloom_end - bloom_start
)

# Kịch bản 4B: Sụp tảo từ 17h ngày thứ 5 trong 18 giờ
crash_start = 4 * 288 + 204
crash_duration = 216
crash_end = crash_start + crash_duration
crash_idx = slice(crash_start, crash_end)

do_base[crash_idx] -= np.linspace(2.5, 3.8, crash_duration)
ph_base[crash_idx] -= np.linspace(0.4, 0.9, crash_duration)
turbidity_base[crash_idx] += np.linspace(
    15.0, 55.0, crash_duration
)

chlorophyll_base[crash_idx] = np.linspace(
    45.0, 8.0, crash_duration
)

# Kịch bản 5: Mưa lớn ngày thứ 7, 14h–18h
rain_start = 6 * 288 + 168
rain_duration = 48
rain_idx = slice(rain_start, rain_start + rain_duration)

salinity_base[rain_idx] -= np.linspace(0, 4.0, rain_duration)
ph_base[rain_idx] -= np.linspace(0, 0.5, rain_duration)
turbidity_base[rain_idx] += np.linspace(0, 35.0, rain_duration)
temp_base[rain_idx] -= np.linspace(0, 2.5, rain_duration)

# ==========================================
# 4. GÁN NHÃN SỰ KIỆN (BƯỚC C)
# ==========================================
# Mỗi cờ thể hiện sự kiện theo kịch bản đã định nghĩa.
# Các cờ có thể đồng thời True trên cùng một bản ghi.

event_flags = {
    "is_heat_stress": day3_mask.copy(),
    "is_oxygen_deficit": np.zeros(n, dtype=bool),
    "is_algal_bloom": np.zeros(n, dtype=bool),
    "is_algal_crash": np.zeros(n, dtype=bool),
    "is_heavy_rain": np.zeros(n, dtype=bool),
}

event_flags["is_oxygen_deficit"][benthic_crisis_idx] = True
event_flags["is_algal_bloom"][bloom_idx] = True
event_flags["is_algal_crash"][crash_idx] = True
event_flags["is_heavy_rain"][rain_idx] = True

# Nhãn chính với thứ tự ưu tiên:
# algal_crash > oxygen_deficit > heat_stress
# > algal_bloom > heavy_rain > normal
event_label = np.full(n, "normal", dtype=object)

event_label[event_flags["is_heavy_rain"]] = "heavy_rain"
event_label[event_flags["is_algal_bloom"]] = "algal_bloom"
event_label[event_flags["is_heat_stress"]] = "heat_stress"
event_label[event_flags["is_oxygen_deficit"]] = "oxygen_deficit"
event_label[event_flags["is_algal_crash"]] = "algal_crash"

# ==========================================
# 5. THÊM NHIỄU VÀ GIỚI HẠN GIÁ TRỊ (BƯỚC D)
# ==========================================
temperature = np.clip(
    temp_base + np.random.normal(0, 0.12, n),
    22.0, 36.0
)
do = np.clip(
    do_base + np.random.normal(0, 0.08, n),
    1.0, 10.0
)
ph = np.clip(
    ph_base + np.random.normal(0, 0.02, n),
    6.8, 9.5
)
salinity = np.clip(
    salinity_base + np.random.normal(0, 0.05, n),
    15.0, 35.0
)
turbidity = np.clip(
    turbidity_base + np.random.normal(0, 0.4, n),
    2.0, 90.0
)

# Chlorophyll-a mô phỏng có nhiễu đo
chlorophyll_a = np.clip(
    chlorophyll_base + np.random.normal(0, 1.2, n),
    0.1, 80.0
)

# ==========================================
# 6. TẠO DATAFRAME VÀ XUẤT CSV (BƯỚC E)
# ==========================================
df = pd.DataFrame({
    "device_id": ["LOBSTER_CAGE_VANPHONG_01"] * n,
    "timestamp": timestamps,
    "temperature": np.round(temperature, 2),
    "ph": np.round(ph, 2),
    "do": np.round(do, 2),
    "salinity": np.round(salinity, 2),
    "turbidity": np.round(turbidity, 2),
    "chlorophyll_a": np.round(chlorophyll_a, 2),
    "event_label": event_label,
    **event_flags,
})

output_file = "lobster_cage_water_quality_synthetic.csv"
df.to_csv(output_file, index=False, encoding="utf-8")

# ==========================================
# 7. KIỂM TRA KẾT QUẢ
# ==========================================
print("=" * 60)
print("ĐÃ TẠO DATASET THÀNH CÔNG!")
print("=" * 60)
print(f"File: {output_file}")
print(f"Số bản ghi: {len(df)}")
print(f"Số cột: {len(df.columns)}")
print(f"Thời gian bắt đầu: {df['timestamp'].iloc[0]}")
print(f"Thời gian kết thúc: {df['timestamp'].iloc[-1]}")
print(f"Số giá trị thiếu: {df.isna().sum().sum()}")

print("\n===== SỐ BẢN GHI THEO NHÃN CHÍNH =====")
print(df["event_label"].value_counts())

print("\n===== SỐ BẢN GHI THEO CỜ SỰ KIỆN =====")
flag_columns = list(event_flags.keys())
print(df[flag_columns].sum())

print("\n===== THỐNG KÊ THÔNG SỐ MÔI TRƯỜNG =====")
measurement_columns = [
    "temperature", "ph", "do",
    "salinity", "turbidity", "chlorophyll_a"
]
print(df[measurement_columns].describe().round(2))

print("\n===== CHLOROPHYLL-A THEO NHÃN =====")
print(
    df.groupby("event_label")["chlorophyll_a"]
    .agg(["count", "mean", "min", "max"])
    .round(2)
)

print("\n5 dòng dữ liệu đầu tiên:")
print(df.head().to_string(index=False))

print("\nDataset đã được lưu tại thư mục hiện tại.")
