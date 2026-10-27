from pathlib import Path
import pandas as pd
import numpy as np

root = Path(__file__).resolve().parent.parent
results = root / "experiments" / "results"
tables = results / "report_tables"

source = pd.read_csv(results / "selected_horizon_test.csv")
reg = pd.read_csv(tables / "regression_comparison.csv")
det = pd.read_csv(tables / "detection_comparison.csv")
cm = pd.read_csv(tables / "confusion_matrices.csv")

checks = {}

# 1. Source metrics must be for horizon 15 minutes.
checks["Source metrics use horizon 15"] = (
    set(source["horizon_minutes"]) == {15}
)

# 2. Regression CSV must match the source metrics.
cols = [
    "horizon_minutes", "model", "train_validation_rows",
    "test_rows", "test_MAE", "test_RMSE", "test_R2"
]

expected = source[cols].sort_values("model").reset_index(drop=True)
actual = reg[cols].sort_values("model").reset_index(drop=True)

checks["Regression CSV matches source metrics"] = (
    len(expected) == len(actual)
    and np.allclose(
        expected.select_dtypes(include="number"),
        actual.select_dtypes(include="number"),
        atol=1e-10,
        rtol=1e-10
    )
    and expected["model"].tolist() == actual["model"].tolist()
)

# 3. Detection and confusion tables must have two models x two thresholds.
checks["Detection table has four combinations"] = len(det) == 4
checks["Confusion matrix table has four combinations"] = len(cm) == 4

expected_pairs = {
    ("Persistence", 3.0),
    ("Persistence", 4.0),
    ("XGBoost", 3.0),
    ("XGBoost", 4.0)
}

checks["Detection table has the expected models and thresholds"] = (
    set(zip(det["model"], det["threshold_mg_L"])) == expected_pairs
)

checks["Confusion table has the expected models and thresholds"] = (
    set(zip(cm["model"], cm["threshold_mg_L"])) == expected_pairs
)

# 4. Every confusion matrix must account for all 302 test rows.
checks["Each confusion matrix totals 302 rows"] = (
    (cm[["TP", "FP", "FN", "TN"]].sum(axis=1) == 302).all()
)

# 5. Actual positive events must equal TP + FN.
checks["Detection actual counts match TP + FN"] = all(
    int(row["TP"] + row["FN"]) == int(row["actual_alerts"])
    for _, row in det.iterrows()
)

print("\n=== REPORT TABLE VERIFICATION ===")
for name, passed in checks.items():
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")

if not all(checks.values()):
    raise SystemExit("\nVERIFICATION FAILED. Check the CSV files.")

print("\nALL REPORT TABLE CHECKS PASSED.")
