
from pathlib import Path
import json

import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = Path(__file__).resolve().parent / "results"

DATASET_NAME = "lobster_cage_water_quality_synthetic.csv"

# Chi su dung 6 features nay de huan luyen mo hinh.
FEATURES = [
    "temperature",
    "ph",
    "do",
    "salinity",
    "turbidity",
    "chlorophyll_a",
]

# Dataset lay mau moi 5 phut.
# Horizon (phut): so buoc shift target.
HORIZONS = {
    5: 1,
    15: 3,
    30: 6,
    60: 12,
}

# Cac nguong canh bao gia dinh, don vi mg/L.
DO_THRESHOLDS = [4.0, 3.0]

TRAIN_RATIO = 0.70
VALIDATION_RATIO = 0.15

XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 3,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "random_state": 42,
    "n_jobs": -1,
    "tree_method": "hist",
}


# ============================================================
# 2. LOAD ORIGINAL DATASET
# ============================================================

def find_dataset():
    """Tim dataset goc ma khong can copy vao experiments."""

    candidates = [
        ROOT_DIR / DATASET_NAME,
        ROOT_DIR / "prepared_data" / DATASET_NAME,
    ]

    for path in candidates:
        if path.is_file():
            return path

    # Tim trong cac thu muc con, bo qua thu muc khong can thiet.
    ignored_dirs = {
        ".git", ".venv", "venv", "__pycache__"
    }

    for path in ROOT_DIR.rglob(DATASET_NAME):
        relative_parts = path.relative_to(ROOT_DIR).parts

        if any(part.lower() in ignored_dirs for part in relative_parts):
            continue

        return path

    raise FileNotFoundError(
        f"Khong tim thay dataset: {DATASET_NAME}\n"
        f"Hay dat file trong {ROOT_DIR} hoac sua DATASET_NAME."
    )


def load_dataset():
    path = find_dataset()
    print(f"Dataset goc: {path}")

    df = pd.read_csv(path)

    required = ["timestamp"] + FEATURES
    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(f"Dataset thieu cot: {missing}")

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], errors="raise"
    )

    for col in FEATURES:
        df[col] = pd.to_numeric(df[col], errors="raise")

    # Chi giu timestamp va 6 features.
    # Loai device_id, event_label va cac co su kien.
    df = df[["timestamp"] + FEATURES].copy()

    if df.isna().any().any():
        raise ValueError(
            "Dataset co gia tri thieu trong cac cot can thiet."
        )

    df = df.sort_values("timestamp").reset_index(drop=True)

    if df["timestamp"].duplicated().any():
        raise ValueError("Dataset co timestamp trung lap.")

    # Kiem tra khoang cach lay mau 5 phut.
    intervals = df["timestamp"].diff().dropna()

    if not intervals.eq(pd.Timedelta(minutes=5)).all():
        raise ValueError(
            "Timestamp khong lien tuc moi 5 phut. "
            "Can kiem tra du lieu truoc khi dung shift theo horizon."
        )

    print(f"So mau: {len(df)}")
    print(f"So cot goc: 14 neu dung dataset goc")
    print(f"So features duoc su dung: {len(FEATURES)}")
    print(f"Bat dau: {df['timestamp'].min()}")
    print(f"Ket thuc: {df['timestamp'].max()}")

    return df


# ============================================================
# 3. CREATE FUTURE TARGET AND CHRONOLOGICAL SPLITS
# ============================================================

def prepare_horizon_data(df, horizon_minutes, steps):
    """
    Target la DO sau steps mau.

    5 phut  -> shift(-1)
    15 phut -> shift(-3)
    30 phut -> shift(-6)
    60 phut -> shift(-12)

    Loai bo cac mau o ranh gioi de target cua split truoc
    khong lan sang khoang thoi gian cua split sau.
    """

    data = df.copy()

    target_col = f"do_future_{horizon_minutes}m"
    data[target_col] = data["do"].shift(-steps)

    # Cac dong cuoi khong co target tuong lai se bi loai.
    data = data.dropna(
        subset=FEATURES + [target_col]
    ).reset_index(drop=True)

    n = len(data)

    train_end = int(n * TRAIN_RATIO)
    validation_end = int(
        n * (TRAIN_RATIO + VALIDATION_RATIO)
    )

    train = data.iloc[:train_end - steps].copy()

    validation = data.iloc[
        train_end:validation_end - steps
    ].copy()

    test = data.iloc[validation_end:].copy()

    if min(len(train), len(validation), len(test)) == 0:
        raise ValueError(
            f"Khong du du lieu cho horizon {horizon_minutes} phut."
        )

    return train, validation, test, target_col


# ============================================================
# 4. EVALUATION METRICS
# ============================================================

def regression_metrics(y_true, y_pred):
    return {
        "MAE": mean_absolute_error(y_true, y_pred),
        "RMSE": np.sqrt(mean_squared_error(y_true, y_pred)),
        "R2": r2_score(y_true, y_pred),
    }


def alert_metrics(y_true, y_pred, threshold):
    """
    DO < threshold: canh bao DO thap.

    TP: phat hien dung.
    FP: canh bao sai.
    FN: bo sot truong hop DO thap.
    TN: khong canh bao dung.
    """

    actual = np.asarray(y_true) < threshold
    predicted = np.asarray(y_pred) < threshold

    tn, fp, fn, tp = confusion_matrix(
        actual,
        predicted,
        labels=[False, True],
    ).ravel()

    return {
        "precision": precision_score(
            actual, predicted, zero_division=0
        ),
        "recall": recall_score(
            actual, predicted, zero_division=0
        ),
        "f1": f1_score(
            actual, predicted, zero_division=0
        ),
        "TP": int(tp),
        "FP": int(fp),
        "FN": int(fn),
        "TN": int(tn),
        "actual_alerts": int(actual.sum()),
    }


def evaluate_predictions(y_true, y_pred, prefix):
    result = {}

    for metric, value in regression_metrics(
        y_true, y_pred
    ).items():
        result[f"{prefix}_{metric}"] = value

    for threshold in DO_THRESHOLDS:
        threshold_name = str(threshold).replace(".", "_")

        metrics = alert_metrics(y_true, y_pred, threshold)

        for metric, value in metrics.items():
            key = (
                f"{prefix}_DO_below_{threshold_name}_{metric}"
            )
            result[key] = value

    return result


# ============================================================
# 5. COMPARE HORIZONS USING VALIDATION
# ============================================================

def compare_horizons(df):
    rows = []
    cache = {}

    for horizon_minutes, steps in HORIZONS.items():
        print("\n" + "=" * 60)
        print(f"HORIZON: {horizon_minutes} MINUTES")
        print("=" * 60)

        train, validation, test, target_col = prepare_horizon_data(
            df, horizon_minutes, steps
        )

        X_train = train[FEATURES]
        y_train = train[target_col]

        X_val = validation[FEATURES]
        y_val = validation[target_col]

        # Baseline: DO hien tai = DO du doan trong tuong lai.
        persistence_pred = validation["do"].to_numpy()

        persistence_row = {
            "horizon_minutes": horizon_minutes,
            "model": "Persistence",
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
        }

        persistence_row.update(
            evaluate_predictions(
                y_val, persistence_pred, "validation"
            )
        )
        rows.append(persistence_row)

        # XGBoost voi cung mot cau hinh cho tat ca horizon.
        model = XGBRegressor(**XGB_PARAMS)
        model.fit(X_train, y_train)

        xgb_pred = model.predict(X_val)

        xgb_row = {
            "horizon_minutes": horizon_minutes,
            "model": "XGBoost",
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
        }

        xgb_row.update(
            evaluate_predictions(y_val, xgb_pred, "validation")
        )
        rows.append(xgb_row)

        cache[horizon_minutes] = {
            "train": train,
            "validation": validation,
            "test": test,
            "target_col": target_col,
        }

        print(
            f"Train: {len(train)} | "
            f"Validation: {len(validation)} | "
            f"Test: {len(test)}"
        )
        print(
            f"Persistence MAE: "
            f"{persistence_row['validation_MAE']:.4f}"
        )
        print(
            f"XGBoost MAE: {xgb_row['validation_MAE']:.4f}"
        )
        print(
            f"XGBoost RMSE: {xgb_row['validation_RMSE']:.4f}"
        )
        print(
            f"XGBoost R2: {xgb_row['validation_R2']:.4f}"
        )

    comparison = pd.DataFrame(rows)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    output_path = RESULTS_DIR / "horizon_comparison.csv"
    comparison.to_csv(output_path, index=False)

    print(f"\nDa luu ket qua validation: {output_path}")

    return comparison, cache


# ============================================================
# 6. FINAL TEST FOR THE SELECTED HORIZON
# ============================================================

def evaluate_selected_horizon(
    selected_horizon,
    cache,
):
    """
    Chi danh gia test sau khi da chon horizon tu validation.

    Huan luyen lai tren train + validation, sau do test
    tren khoang thoi gian chua dung de huan luyen.
    """

    selected = cache[selected_horizon]

    train = selected["train"]
    validation = selected["validation"]
    test = selected["test"]
    target_col = selected["target_col"]

    train_validation = pd.concat(
        [train, validation],
        ignore_index=True,
    )

    model = XGBRegressor(**XGB_PARAMS)
    model.fit(
        train_validation[FEATURES],
        train_validation[target_col],
    )

    y_test = test[target_col].to_numpy()
    xgb_pred = model.predict(test[FEATURES])
    persistence_pred = test["do"].to_numpy()

    test_rows = []

    for model_name, predictions in [
        ("Persistence", persistence_pred),
        ("XGBoost", xgb_pred),
    ]:
        row = {
            "horizon_minutes": selected_horizon,
            "model": model_name,
            "train_validation_rows": len(train_validation),
            "test_rows": len(test),
        }

        row.update(
            evaluate_predictions(y_test, predictions, "test")
        )
        test_rows.append(row)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    metrics_path = RESULTS_DIR / "selected_horizon_test.csv"
    pd.DataFrame(test_rows).to_csv(metrics_path, index=False)

    predictions_df = pd.DataFrame({
        "timestamp": test["timestamp"].to_numpy(),
        "do_current": test["do"].to_numpy(),
        "do_actual_future": y_test,
        "do_predicted_future": xgb_pred,
        "persistence_predicted_future": persistence_pred,
    })

    for threshold in DO_THRESHOLDS:
        name = str(threshold).replace(".", "_")

        predictions_df[f"actual_alert_below_{name}"] = (
            predictions_df["do_actual_future"] < threshold
        )

        predictions_df[f"xgb_alert_below_{name}"] = (
            predictions_df["do_predicted_future"] < threshold
        )

    predictions_path = (
        RESULTS_DIR / "selected_horizon_predictions.csv"
    )
    predictions_df.to_csv(predictions_path, index=False)

    model_path = RESULTS_DIR / "selected_horizon_model.json"
    model.save_model(str(model_path))

    metadata = {
        "selected_horizon_minutes": selected_horizon,
        "target_column": target_col,
        "features": FEATURES,
        "thresholds_mg_l": DO_THRESHOLDS,
        "split_ratios": {
            "train": TRAIN_RATIO,
            "validation": VALIDATION_RATIO,
            "test": 1 - TRAIN_RATIO - VALIDATION_RATIO,
        },
        "model_parameters": XGB_PARAMS,
        "dataset_type": "synthetic",
        "note": (
            "The DO thresholds are experimental assumptions, "
            "not verified lobster-specific biological standards."
        ),
    }

    metadata_path = RESULTS_DIR / "experiment_metadata.json"

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=4, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"TEST RESULTS - HORIZON {selected_horizon} MINUTES")
    print("=" * 60)
    print(pd.DataFrame(test_rows).to_string(index=False))

    print("\nDa luu:")
    print(f"- {metrics_path}")
    print(f"- {predictions_path}")
    print(f"- {model_path}")
    print(f"- {metadata_path}")


# ============================================================
# 7. MAIN
# ============================================================

def main():
    df = load_dataset()

    comparison, cache = compare_horizons(df)

    xgb_validation = comparison[
        comparison["model"] == "XGBoost"
    ].sort_values("validation_MAE")

    print("\n" + "=" * 60)
    print("XGBOOST RANKING - VALIDATION")
    print("=" * 60)

    columns_to_show = [
        "horizon_minutes",
        "validation_MAE",
        "validation_RMSE",
        "validation_R2",
        "validation_DO_below_4_0_recall",
        "validation_DO_below_4_0_FN",
        "validation_DO_below_3_0_recall",
        "validation_DO_below_3_0_FN",
    ]

    print(xgb_validation[columns_to_show].to_string(index=False))

    print(
        "\nHay chon horizon dua tren validation, "
        "khong chon dua tren test."
    )
    print(
        "Can can nhac sai so DO, recall, so lan bo sot "
        "va thoi gian canh bao huu ich."
    )

    while True:
        choice = input(
            "\nNhap horizon de danh gia test (5/15/30/60): "
        ).strip()

        try:
            selected_horizon = int(choice)
        except ValueError:
            print("Vui long nhap 5, 15, 30 hoac 60.")
            continue

        if selected_horizon in HORIZONS:
            break

        print("Lua chon khong hop le. Hay nhap 5, 15, 30 hoac 60.")

    evaluate_selected_horizon(selected_horizon, cache)


if __name__ == "__main__":
    main()
