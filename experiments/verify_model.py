import json
from pathlib import Path
import pandas as pd
import xgboost as xgb

root = Path(__file__).resolve().parent
results = root / "results"

metadata_path = results / "experiment_metadata.json"
metrics_path = results / "selected_horizon_test.csv"
predictions_path = results / "selected_horizon_predictions.csv"
model_path = results / "selected_horizon_model.json"

metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metrics = pd.read_csv(metrics_path)
predictions = pd.read_csv(predictions_path)

booster = xgb.Booster()
booster.load_model(str(model_path))

checks = {
    "Metadata horizon is 15 minutes":
        metadata.get("selected_horizon_minutes") == 15,
    "Metadata target is do_future_15m":
        metadata.get("target_column") == "do_future_15m",
    "Test metrics contain only horizon 15":
        set(metrics["horizon_minutes"].unique()) == {15},
    "Both expected models are present":
        set(metrics["model"]) == {"Persistence", "XGBoost"},
    "Prediction file has 302 rows":
        len(predictions) == 302,
    "Model has six input features":
        booster.num_features() == 6,
    "Model has 200 boosting rounds":
        booster.num_boosted_rounds() == 200,
}

print("\n=== MODEL ARTIFACT VERIFICATION ===")
for label, passed in checks.items():
    print(f"[{'PASS' if passed else 'FAIL'}] {label}")

print("\n=== MODEL DETAILS ===")
print("Model file:", model_path)
print("File size:", model_path.stat().st_size, "bytes")
print("XGBoost version:", xgb.__version__)
print("Boosting rounds:", booster.num_boosted_rounds())
print("Number of features:", booster.num_features())
print("Feature names embedded in model:", booster.feature_names)
print("Metadata features:", metadata.get("features"))
print("Model parameters in metadata:")
print(json.dumps(metadata.get("model_parameters"), indent=2))

if booster.feature_names is None:
    print(
        "\nNOTE: Feature names are not embedded in the model. "
        "The six-feature count is verified, but the feature order must "
        "be confirmed from the training script and metadata."
    )

print("\n=== TEST METRICS ===")
print(metrics[["horizon_minutes", "model", "train_validation_rows",
               "test_rows", "test_MAE", "test_RMSE", "test_R2"]]
      .to_string(index=False))

if not all(checks.values()):
    raise SystemExit(
        "\nVERIFICATION FAILED: investigate the failed checks before "
        "using this artifact in the report."
    )

print("\nAll automated checks passed. Review feature order and "
      "training-script consistency before declaring the artifact fully verified.")
