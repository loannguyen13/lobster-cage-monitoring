from pathlib import Path
import json
import numpy as np
import pandas as pd
import xgboost as xgb

project = Path(__file__).resolve().parent.parent
results = project / "experiments" / "results"
test_path = project / "prepared_data" / "test.csv"
model_path = results / "selected_horizon_model.json"
pred_path = results / "selected_horizon_predictions.csv"
metadata_path = results / "experiment_metadata.json"

features = [
    "temperature", "ph", "do",
    "salinity", "turbidity", "chlorophyll_a"
]
tol = 1e-5

metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
test = pd.read_csv(test_path)
saved = pd.read_csv(pred_path)

test["timestamp"] = pd.to_datetime(test["timestamp"])
saved["timestamp"] = pd.to_datetime(saved["timestamp"])

assert metadata["selected_horizon_minutes"] == 15
assert metadata["target_column"] == "do_future_15m"
assert metadata["features"] == features

assert not test["timestamp"].duplicated().any()
assert not saved["timestamp"].duplicated().any()

data = test.merge(
    saved,
    on="timestamp",
    how="outer",
    indicator=True,
    validate="one_to_one",
    suffixes=("_test", "_saved")
)

if not (data["_merge"] == "both").all():
    raise ValueError("Test timestamps and saved prediction timestamps differ.")

data = data.drop(columns="_merge").sort_values("timestamp").reset_index(drop=True)

booster = xgb.Booster()
booster.load_model(str(model_path))

if booster.feature_names != features:
    raise ValueError(f"Unexpected model feature order: {booster.feature_names}")

X = data[features].astype(float)
recreated = booster.predict(xgb.DMatrix(X, feature_names=features))

def max_diff(a, b):
    return float(np.max(np.abs(
        np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    )))

checks = {
    "Horizon is 15 minutes": metadata["selected_horizon_minutes"] == 15,
    "Test contains 302 rows": len(data) == 302,
    "Model has 200 boosting rounds": booster.num_boosted_rounds() == 200,
    "Prediction recreation matches saved predictions":
        max_diff(recreated, data["do_predicted_future"]) <= tol,
    "Future DO target matches saved actual DO":
        max_diff(data["do_future_15m"], data["do_actual_future"]) <= tol,
    "Current DO matches saved current DO":
        max_diff(data["do"], data["do_current"]) <= tol,
    "Persistence prediction equals current DO":
        max_diff(data["do_current"], data["persistence_predicted_future"]) <= tol,
}

actual = data["do_actual_future"].astype(float)
predicted = data["do_predicted_future"].astype(float)

for threshold in (4.0, 3.0):
    suffix = str(threshold).replace(".", "_")
    checks[f"Actual DO < {threshold} flags are correct"] = np.array_equal(
        actual < threshold,
        data[f"actual_alert_below_{suffix}"].astype(bool)
    )
    checks[f"XGBoost DO < {threshold} flags are correct"] = np.array_equal(
        predicted < threshold,
        data[f"xgb_alert_below_{suffix}"].astype(bool)
    )

print("\n=== REPRODUCIBILITY CHECK ===")
for name, passed in checks.items():
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")

print(f"\nMaximum prediction difference: {max_diff(recreated, data['do_predicted_future']):.10f}")
print(f"Model feature order: {booster.feature_names}")
print(f"Test rows: {len(data)}")

if not all(checks.values()):
    raise SystemExit("\nCHECK FAILED: investigate before finalizing the report.")

print("\nALL REPRODUCIBILITY CHECKS PASSED.")
