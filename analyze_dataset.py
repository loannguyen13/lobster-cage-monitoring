
import pandas as pd
import matplotlib.pyplot as plt

# ==========================================
# 1. ĐỌC DATASET
# ==========================================
df = pd.read_csv("lobster_cage_water_quality_synthetic.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"])

# ==========================================
# 2. KIỂM TRA CẤU TRÚC DỮ LIỆU
# ==========================================
print("===== TỔNG QUAN DATASET =====")
print("Số dòng, số cột:", df.shape)

print("\nTên các cột:")
print(df.columns.tolist())

print("\n===== DỮ LIỆU THIẾU =====")
print(df.isnull().sum())

print("\n===== BẢN GHI TRÙNG =====")
print("Số dòng trùng:", df.duplicated().sum())
print("Timestamp trùng:", df["timestamp"].duplicated().sum())

# ==========================================
# 3. THỐNG KÊ CÁC THÔNG SỐ MÔI TRƯỜNG
# ==========================================
columns = [
    "temperature",
    "ph",
    "do",
    "salinity",
    "turbidity",
    "chlorophyll_a"
]

print("\n===== THỐNG KÊ CÁC THÔNG SỐ =====")
print(df[columns].describe().round(2))

# ==========================================
# 4. THỐNG KÊ NHÃN SỰ KIỆN
# ==========================================
print("\n===== SỐ LƯỢNG BẢN GHI THEO EVENT_LABEL =====")
event_counts = df["event_label"].value_counts()
print(event_counts)

print("\n===== TỶ LỆ CÁC SỰ KIỆN (%) =====")
print(
    (df["event_label"].value_counts(normalize=True) * 100)
    .round(2)
)

# Thống kê chlorophyll-a theo từng sự kiện
print("\n===== CHLOROPHYLL-A THEO SỰ KIỆN =====")
print(
    df.groupby("event_label")["chlorophyll_a"]
    .agg(["count", "mean", "min", "max"])
    .round(2)
)

# ==========================================
# 5. VẼ BIỂU ĐỒ CÁC THÔNG SỐ THEO THỜI GIAN
# ==========================================
metrics = [
    ("temperature", "Temperature (°C)"),
    ("ph", "pH"),
    ("do", "Dissolved Oxygen (mg/L)"),
    ("salinity", "Salinity (ppt)"),
    ("turbidity", "Turbidity (NTU)"),
    ("chlorophyll_a", "Chlorophyll-a (µg/L)")
]

fig, axes = plt.subplots(
    len(metrics), 1,
    figsize=(15, 17),
    sharex=True
)

for ax, (column, label) in zip(axes, metrics):
    ax.plot(
        df["timestamp"],
        df[column],
        linewidth=0.8
    )
    ax.set_ylabel(label)
    ax.grid(True, alpha=0.3)

axes[-1].set_xlabel("Time")

fig.suptitle(
    "Synthetic Lobster Cage Water Quality - 7 Days",
    fontsize=14
)

plt.tight_layout()
plt.savefig("dataset_timeseries.png", dpi=150)
plt.show()

print("\nĐã lưu biểu đồ: dataset_timeseries.png")

# ==========================================
# 6. VẼ BIỂU ĐỒ PHÂN BỐ EVENT_LABEL
# ==========================================
plt.figure(figsize=(10, 5))

event_counts.plot(
    kind="bar",
    rot=30
)

plt.title("Distribution of Event Labels")
plt.xlabel("Event Label")
plt.ylabel("Number of Records")
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()

plt.savefig("event_label_distribution.png", dpi=150)
plt.show()

print("Đã lưu biểu đồ: event_label_distribution.png")

# ==========================================
# 7. HIỂN THỊ EVENT_LABEL THEO THỜI GIAN
# ==========================================
event_mapping = {
    "normal": 0,
    "heavy_rain": 1,
    "algal_bloom": 2,
    "heat_stress": 3,
    "oxygen_deficit": 4,
    "algal_crash": 5
}

df["event_code"] = df["event_label"].map(event_mapping)

plt.figure(figsize=(15, 4))

plt.scatter(
    df["timestamp"],
    df["event_code"],
    s=8
)

plt.yticks(
    list(event_mapping.values()),
    list(event_mapping.keys())
)

plt.title("Event Labels Over Time")
plt.xlabel("Time")
plt.ylabel("Event Label")
plt.grid(True, alpha=0.3)
plt.tight_layout()

plt.savefig("event_labels_timeseries.png", dpi=150)
plt.show()

print("Đã lưu biểu đồ: event_labels_timeseries.png")

print("\n===== HOÀN TẤT PHÂN TÍCH DATASET =====")
