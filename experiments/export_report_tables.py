from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parent
results = root / "results"
out = results / "report_tables"
out.mkdir(parents=True, exist_ok=True)

metrics = pd.read_csv(results / "selected_horizon_test.csv")

if set(metrics["horizon_minutes"].unique()) != {15}:
    raise ValueError("Expected only horizon_minutes = 15.")

if set(metrics["model"]) != {"Persistence", "XGBoost"}:
    raise ValueError("Expected Persistence and XGBoost.")

# 1. Regression comparison
regression = metrics[
    ["horizon_minutes", "model", "train_validation_rows", "test_rows",
     "test_MAE", "test_RMSE", "test_R2"]
].copy()

regression.to_csv(out / "regression_comparison.csv", index=False)

# 2. Detection metrics and confusion matrix
rows = []

for _, row in metrics.iterrows():
    for threshold in ("4_0", "3_0"):
        prefix = f"test_DO_below_{threshold}_"

        rows.append({
            "horizon_minutes": int(row["horizon_minutes"]),
            "model": row["model"],
            "threshold_mg_L": float(threshold.replace("_", ".")),
            "precision": row[prefix + "precision"],
            "recall": row[prefix + "recall"],
            "f1": row[prefix + "f1"],
            "TP": int(row[prefix + "TP"]),
            "FP": int(row[prefix + "FP"]),
            "FN": int(row[prefix + "FN"]),
            "TN": int(row[prefix + "TN"]),
            "actual_alerts": int(row[prefix + "actual_alerts"]),
        })

detection = pd.DataFrame(rows)
detection.to_csv(out / "detection_comparison.csv", index=False)

confusion = detection[
    ["horizon_minutes", "model", "threshold_mg_L",
     "TP", "FP", "FN", "TN"]
].copy()

confusion.to_csv(out / "confusion_matrices.csv", index=False)

print("Export complete:")
print("Regression:", out / "regression_comparison.csv")
print("Detection:", out / "detection_comparison.csv")
print("Confusion:", out / "confusion_matrices.csv")

print("\nRegression comparison:")
print(regression.to_string(index=False))

print("\nDetection comparison:")
print(detection.to_string(index=False))

print("\nConfusion matrices:")
print(confusion.to_string(index=False))
