
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# BƯỚC 1 — PREPARE DATASET CHO MÔ HÌNH XGBOOST
# Dự báo DO trước 15 phút
# ============================================================


# ------------------------------------------------------------
# 1. CẤU HÌNH
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DATA_PATH = BASE_DIR / "lobster_cage_water_quality_synthetic.csv"
OUTPUT_DIR = BASE_DIR / "prepared_data"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "do_future_15m"
FORECAST_STEPS = 3
INTERVAL_MINUTES = 5

FEATURES = [
    "temperature",
    "ph",
    "do",
    "salinity",
    "turbidity",
    "chlorophyll_a",
]

REQUIRED_COLUMNS = [
    "device_id",
    "timestamp",
    "temperature",
    "ph",
    "do",
    "salinity",
    "turbidity",
    "chlorophyll_a",
]


# ------------------------------------------------------------
# 2. ĐỌC DATASET
# ------------------------------------------------------------

print("=" * 65)
print("BƯỚC 1.1 — ĐỌC VÀ KIỂM TRA DATASET")
print("=" * 65)

if not DATA_PATH.exists():
    raise FileNotFoundError(
        f"Không tìm thấy file dataset: {DATA_PATH}"
    )

df = pd.read_csv(DATA_PATH)

print("Dataset shape ban đầu:", df.shape)
print("Columns:", df.columns.tolist())

# Kiểm tra các cột bắt buộc
missing_columns = [
    col for col in REQUIRED_COLUMNS
    if col not in df.columns
]

if missing_columns:
    raise ValueError(
        f"Dataset thiếu các cột bắt buộc: {missing_columns}"
    )

print("\nKiểu dữ liệu ban đầu:")
print(df.dtypes)

print("\n5 dòng đầu:")
print(df.head())

print("\nMissing values theo cột:")
print(df.isnull().sum())

print("\nSố dòng trùng hoàn toàn:", df.duplicated().sum())

if df.empty:
    raise ValueError("Dataset không có dữ liệu.")

if df[REQUIRED_COLUMNS].isnull().any().any():
    raise ValueError(
        "Có missing values trong các cột cần thiết. "
        "Hãy kiểm tra dữ liệu trước khi tiếp tục."
    )


# ------------------------------------------------------------
# 3. CHUẨN HÓA TIMESTAMP VÀ KIỂM TRA CHUỖI THỜI GIAN
# ------------------------------------------------------------

print("\n" + "=" * 65)
print("BƯỚC 1.2 — KIỂM TRA CHUỖI THỜI GIAN")
print("=" * 65)

# Chuyển timestamp từ str sang datetime
df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    errors="coerce"
)

print("Timestamp dtype sau chuyển đổi:", df["timestamp"].dtype)

if df["timestamp"].isna().any():
    raise ValueError(
        "Có timestamp không hợp lệ. "
        "Hãy kiểm tra các giá trị timestamp trong CSV."
    )

# Sắp xếp tăng dần theo thời gian
df = df.sort_values("timestamp").reset_index(drop=True)

# Kiểm tra số thiết bị
device_count = df["device_id"].nunique()

print("Số thiết bị:", device_count)
print("Danh sách thiết bị:", df["device_id"].unique())

# Code hiện tại giả định chỉ có một thiết bị
if device_count != 1:
    raise ValueError(
        "Dataset có nhiều hơn một thiết bị. "
        "Cần xử lý chuỗi thời gian riêng theo từng device_id."
    )

# Kiểm tra timestamp trùng
duplicate_timestamps = df["timestamp"].duplicated().sum()

print("Timestamp bị trùng:", duplicate_timestamps)

if duplicate_timestamps > 0:
    raise ValueError(
        "Có timestamp trùng. Không thể tiếp tục "
        "trước khi xác minh các bản ghi trùng."
    )

# Kiểm tra khoảng cách giữa các lần đo
time_diff = df["timestamp"].diff()

expected_interval = pd.Timedelta(
    minutes=INTERVAL_MINUTES
)

invalid_intervals = (
    time_diff.dropna() != expected_interval
).sum()

print("\nPhân bố khoảng cách giữa các lần đo:")
print(time_diff.value_counts().sort_index())

print("Số khoảng cách khác 5 phút:", invalid_intervals)

if invalid_intervals > 0:
    raise ValueError(
        "Chuỗi thời gian không liên tục mỗi 5 phút. "
        "Cần xử lý khoảng thời gian thiếu trước khi tạo target."
    )

print("Thời điểm đầu:", df["timestamp"].min())
print("Thời điểm cuối:", df["timestamp"].max())
print("Dataset shape sau kiểm tra:", df.shape)


# ------------------------------------------------------------
# 4. KIỂM TRA CÁC BIẾN SỐ
# ------------------------------------------------------------

print("\n" + "=" * 65)
print("BƯỚC 1.3 — KIỂM TRA FEATURES")
print("=" * 65)

# Chuyển các cột môi trường sang kiểu số nếu cần
for col in FEATURES:
    df[col] = pd.to_numeric(df[col], errors="coerce")

if df[FEATURES].isnull().any().any():
    raise ValueError(
        "Có giá trị môi trường không phải số hoặc bị thiếu."
    )

# Kiểm tra NaN, +inf, -inf
numeric_values = df[FEATURES].to_numpy(dtype=float)

if not np.isfinite(numeric_values).all():
    raise ValueError(
        "Có giá trị NaN hoặc vô cực trong features."
    )

print("Số features ban đầu:", len(FEATURES))
print("Features:", FEATURES)

print("\nThống kê các features:")
print(df[FEATURES].describe().round(3))


# ------------------------------------------------------------
# 5. TẠO TARGET DỰ BÁO DO SAU 15 PHÚT
# ------------------------------------------------------------

print("\n" + "=" * 65)
print("BƯỚC 1.4 — TẠO TARGET")
print("=" * 65)

# Mỗi dòng cách nhau 5 phút.
# shift(-3): lấy DO ở thời điểm hiện tại + 15 phút.
df[TARGET] = df["do"].shift(-FORECAST_STEPS)

# Chỉ lấy timestamp, features và target.
# Không đưa event_label hoặc các event flags vào mô hình.
ml_df = df[
    ["timestamp", *FEATURES, TARGET]
].copy()

rows_before = len(ml_df)

# 3 dòng cuối không có target vì không có dữ liệu
# DO của thời điểm tương lai tương ứng.
ml_df = ml_df.dropna(subset=[TARGET]).reset_index(drop=True)

print("Target:", TARGET)
print("Dự báo trước:", FORECAST_STEPS * INTERVAL_MINUTES, "phút")
print("Số dòng trước khi tạo target:", rows_before)
print("Số dòng sau khi tạo target:", len(ml_df))
print("Số dòng không có target bị loại:", rows_before - len(ml_df))

if ml_df[TARGET].isnull().any():
    raise ValueError("Target vẫn còn missing values.")

if not np.isfinite(ml_df[TARGET].to_numpy(dtype=float)).all():
    raise ValueError("Target có giá trị không hữu hạn.")

print("\nThống kê target:")
print(ml_df[TARGET].describe().round(3))

print(
    "\nSố mẫu có DO tương lai < 4.0 mg/L:",
    int((ml_df[TARGET] < 4.0).sum())
)

print(
    "Số mẫu có DO tương lai < 3.0 mg/L:",
    int((ml_df[TARGET] < 3.0).sum())
)


# ------------------------------------------------------------
# 6. CHIA TRAIN / VALIDATION / TEST THEO THỜI GIAN
# ------------------------------------------------------------

print("\n" + "=" * 65)
print("BƯỚC 1.5 — CHIA TẬP DỮ LIỆU")
print("=" * 65)

# Không shuffle dữ liệu chuỗi thời gian.
# Tỉ lệ ranh giới ban đầu: 70% / 15% / 15%.
n = len(ml_df)

train_boundary = int(n * 0.70)
validation_boundary = int(n * 0.85)

# Vì target tại t dùng DO tại t + 15 phút,
# loại 3 dòng ngay trước mỗi ranh giới.
# Điều này tránh để target của tập trước sử dụng
# DO thuộc khoảng thời gian của tập kế tiếp.

train_df = ml_df.iloc[
    :max(0, train_boundary - FORECAST_STEPS)
].copy()

validation_df = ml_df.iloc[
    train_boundary:
    max(train_boundary, validation_boundary - FORECAST_STEPS)
].copy()

test_df = ml_df.iloc[validation_boundary:].copy()

if min(
    len(train_df),
    len(validation_df),
    len(test_df)
) == 0:
    raise ValueError(
        "Một tập dữ liệu rỗng. Hãy kiểm tra kích thước dataset "
        "và cách chia tập."
    )

print("Tổng số dòng có target:", n)
print("Train:", len(train_df))
print("Validation:", len(validation_df))
print("Test:", len(test_df))
print(
    "Số dòng bị loại tại các ranh giới:",
    n - len(train_df) - len(validation_df) - len(test_df)
)


# ------------------------------------------------------------
# 7. KIỂM TRA CÁC TẬP DỮ LIỆU
# ------------------------------------------------------------

print("\n" + "=" * 65)
print("BƯỚC 1.6 — KIỂM TRA KẾT QUẢ CHIA TẬP")
print("=" * 65)

splits = {
    "train": train_df,
    "validation": validation_df,
    "test": test_df,
}

for split_name, split_df in splits.items():
    print(f"\n[{split_name.upper()}]")
    print("Số dòng:", len(split_df))
    print(
        "Thời gian features:",
        split_df["timestamp"].min(),
        "->",
        split_df["timestamp"].max()
    )

    print(
        "DO tương lai < 4.0 mg/L:",
        int((split_df[TARGET] < 4.0).sum())
    )

    print(
        "DO tương lai < 3.0 mg/L:",
        int((split_df[TARGET] < 3.0).sum())
    )

    print(
        "Target min / max:",
        round(split_df[TARGET].min(), 3),
        "/",
        round(split_df[TARGET].max(), 3)
    )

# Xác nhận các features không chứa target
assert TARGET not in FEATURES

# Xác nhận thời gian được giữ theo thứ tự tăng dần
for split_name, split_df in splits.items():
    if not split_df["timestamp"].is_monotonic_increasing:
        raise ValueError(
            f"Tập {split_name} không được sắp xếp theo thời gian."
        )


# ------------------------------------------------------------
# 8. LƯU DATASET ĐÃ CHUẨN BỊ
# ------------------------------------------------------------

print("\n" + "=" * 65)
print("BƯỚC 1.7 — LƯU DỮ LIỆU")
print("=" * 65)

# Dataset đầy đủ có target, trước khi chia tập.
ml_df.to_csv(
    OUTPUT_DIR / "ml_dataset.csv",
    index=False
)

# Lưu riêng từng tập để các bước tiếp theo sử dụng.
train_df.to_csv(
    OUTPUT_DIR / "train.csv",
    index=False
)

validation_df.to_csv(
    OUTPUT_DIR / "validation.csv",
    index=False
)

test_df.to_csv(
    OUTPUT_DIR / "test.csv",
    index=False
)

print("Đã lưu các file vào:", OUTPUT_DIR)
print("- ml_dataset.csv")
print("- train.csv")
print("- validation.csv")
print("- test.csv")

print("\nTimestamp dtype trong df:", df["timestamp"].dtype)
print("Timestamp dtype trong ml_df:", ml_df["timestamp"].dtype)


print("\n========== KIỂM TRA PHÂN BỐ DO ==========")

for name, split_df in splits.items():
    y = split_df[TARGET]

    print(f"\n{name.upper()}")
    print("DO < 3.0:", int((y < 3.0).sum()))
    print("3.0 <= DO < 4.0:", int(((y >= 3.0) & (y < 4.0)).sum()))
    print("DO >= 4.0:", int((y >= 4.0).sum()))

print("\nHOÀN THÀNH BƯỚC 1 — PREPARE DATASET")
