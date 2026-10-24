# Dissolved Oxygen (DO) Prediction — Model Development

## 1. Overview

This directory contains the model development, evaluation, and verification scripts for predicting dissolved oxygen (DO) levels in lobster cage aquaculture.

The objective is to predict the dissolved oxygen concentration **15 minutes into the future** and evaluate whether the predictions can support early warnings of potentially low-DO conditions.

The selected model is **XGBoost Regressor**. A **Persistence baseline**, which assumes that future DO remains equal to the current DO, is used for comparison.

> **Important:** The experiments use synthetic data. The results demonstrate the model development and evaluation workflow, not validated performance in real aquaculture environments.

## 2. Dataset

### 2.1 Data source

The dataset is `lobster_cage_water_quality_synthetic.csv`.

| Property | Value |
|---|---|
| Data type | Synthetic water-quality time series |
| Number of records | 2,016 |
| Time range | October 1–7, 2026 |
| Sampling interval | 5 minutes |
| Number of input features | 6 |
| Prediction target | DO concentration 15 minutes ahead |

The dataset contains measurements of water temperature, pH, dissolved oxygen, salinity, turbidity, and chlorophyll-a.

### 2.2 Input features

The model uses the following six features:

| Feature | Description |
|---|---|
| `temperature` | Water temperature |
| `ph` | Water pH |
| `do` | Current dissolved oxygen concentration |
| `salinity` | Water salinity |
| `turbidity` | Water turbidity |
| `chlorophyll_a` | Chlorophyll-a concentration |

The target variable is `do_future_15m`, calculated by shifting the current DO series three rows forward:

```python
df["do_future_15m"] = df["do"].shift(-3)
```

Since measurements are collected every five minutes, three rows correspond to a 15-minute prediction horizon.

Scenario labels and event flags are excluded from the model inputs to reduce the risk of synthetic scenario information leaking into the predictions.

## 3. Data Preparation and Splitting

The prepared dataset is stored in `prepared_data/`.

| Dataset | Records |
|---|---:|
| Training set | 1,406 |
| Validation set | 299 |
| Test set | 302 |
| Total retained records | 2,007 |

The data is split **chronologically**, rather than randomly, to preserve the time-series order and better reflect the intended forecasting setting.

Six additional rows are excluded around the split boundaries to reduce leakage caused by overlapping target horizons.

The original dataset contains 2,016 records. After removing rows without valid future targets and applying the split-boundary purge, 2,007 records remain across the three subsets.

- **Training set:** model fitting.
- **Validation set:** horizon comparison and model selection.
- **Test set:** final evaluation of the selected 15-minute forecasting model.

The test set is kept separate from model selection.

## 4. Models and Experimental Configuration

### 4.1 XGBoost Regressor

The selected XGBoost configuration is:

```python
{
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
    "tree_method": "hist"
}
```

The model estimates the future DO concentration from the six water-quality features.

### 4.2 Persistence Baseline

The Persistence baseline predicts that the future DO concentration equals the current DO concentration:

```python
do_predicted_future = do_current
```

This is a simple reference model for determining whether a more complex model provides meaningful predictive improvement.

Both models are evaluated using the same test records and prediction horizon.

### 4.3 Prediction Horizons

The horizon comparison experiment evaluates:

- 5 minutes
- 15 minutes
- 30 minutes
- 60 minutes

The 15-minute horizon is selected as the primary horizon for the final model evaluation.

## 5. Test Results

### 5.1 Regression Performance

The following results are from the 302-record test set for the selected 15-minute horizon.

| Metric | Persistence | XGBoost |
|---|---:|---:|
| MAE (mg/L) | 0.130795 | 0.147501 |
| RMSE (mg/L) | 0.164812 | 0.204699 |
| R² | 0.986727 | 0.979525 |

**Interpretation:** Persistence achieves lower MAE and RMSE and a higher R² than XGBoost on this test set. Therefore, XGBoost does not outperform the baseline in overall regression accuracy.

### 5.2 Low-DO Event Detection

The predicted DO concentration is also evaluated against two low-DO thresholds:

- **DO < 4.0 mg/L**
- **DO < 3.0 mg/L**

A prediction below a threshold is treated as a predicted low-DO event. The event is compared with the actual future DO value at the same threshold.

| Threshold | Model | Precision | Recall | F1-score |
|---|---|---:|---:|---:|
| DO < 4.0 mg/L | Persistence | 0.938776 | 0.938776 | 0.938776 |
| DO < 4.0 mg/L | XGBoost | 0.940000 | 0.959184 | 0.949495 |
| DO < 3.0 mg/L | Persistence | 0.875000 | 0.875000 | 0.875000 |
| DO < 3.0 mg/L | XGBoost | 0.909091 | 0.833333 | 0.869565 |

XGBoost achieves a higher recall at the 4.0 mg/L threshold but a lower recall at the 3.0 mg/L threshold. It therefore does not consistently outperform Persistence across the two event thresholds.

### 5.3 Confusion Matrices

The confusion matrices below use the convention:

- **TP:** correctly predicted low-DO events.
- **FP:** predicted low-DO events that did not occur.
- **FN:** actual low-DO events that were missed.
- **TN:** correctly predicted non-event records.

#### Threshold: DO < 4.0 mg/L

| Model | TP | FP | FN | TN |
|---|---:|---:|---:|---:|
| Persistence | 46 | 3 | 3 | 250 |
| XGBoost | 47 | 3 | 2 | 250 |

#### Threshold: DO < 3.0 mg/L

| Model | TP | FP | FN | TN |
|---|---:|---:|---:|---:|
| Persistence | 21 | 3 | 3 | 275 |
| XGBoost | 20 | 2 | 4 | 276 |

Each confusion matrix accounts for all 302 test records.

The results illustrate a trade-off between regression accuracy and low-DO event detection. The preferred model depends on the application's priorities, particularly the cost of missed low-DO events versus false alarms.

## 6. Repository Structure

The relevant files in this directory are:

```text
experiments/
├── README.md
├── compare_horizons.py
├── export_report_tables.py
├── verify_model.py
├── verify_reproducibility.py
├── verify_report_tables.py
└── results/
    ├── experiment_metadata.json
    ├── horizon_comparison.csv
    ├── selected_horizon_model.json
    ├── selected_horizon_predictions.csv
    ├── selected_horizon_test.csv
    └── report_tables/
        ├── regression_comparison.csv
        ├── detection_comparison.csv
        └── confusion_matrices.csv
```

The prepared datasets are stored separately in `prepared_data/`.

## 7. Running the Experiments and Verification

Run the commands from the repository root using the project's Python virtual environment.

### 7.1 Compare Prediction Horizons

```powershell
python experiments/compare_horizons.py
```

This script compares the configured prediction horizons using XGBoost and the Persistence baseline.

### 7.2 Export Report Tables

```powershell
python experiments/export_report_tables.py
```

This script exports the regression metrics, low-DO detection metrics, and confusion matrices used in the report.

### 7.3 Verify the Model Artifact

```powershell
python experiments/verify_model.py
```

This checks the saved model artifact and its metadata, including the selected horizon, target, features, and model configuration.

### 7.4 Verify Reproducibility

```powershell
python experiments/verify_reproducibility.py
```

This checks whether predictions and derived results can be reproduced from the saved model and test dataset.

### 7.5 Verify Report Tables

```powershell
python experiments/verify_report_tables.py
```

This checks that the exported report tables agree with the source metrics and that the confusion matrices account for the expected test records.

Ensure that the required dependencies are installed and that the prepared datasets and result files are available at the expected paths before running the verification scripts.

## 8. Limitations

The current experiments have several important limitations:

1. **Synthetic data:** The dataset is generated rather than collected from real lobster cages. The results do not establish real-world forecasting accuracy.
2. **Short observation period:** The dataset covers only seven days and may not represent seasonal changes, weather variations, or longer-term water-quality dynamics.
3. **Single-device scenario:** The experiment does not evaluate generalization across multiple sensors, cages, farms, or locations.
4. **Baseline performance:** Persistence outperforms XGBoost on regression metrics in the selected test experiment. The added value of the more complex model remains to be established.
5. **Threshold validation:** The 4.0 mg/L and 3.0 mg/L thresholds are experimental alert thresholds for this project and should be validated against appropriate aquaculture guidance and local operating conditions.
6. **Operational validation:** The system has not been validated through real-time deployment or field trials. Alert reliability, sensor calibration, communication failures, and practical response time remain to be evaluated.

## 9. Next Steps

Future work should focus on:

- Collecting real water-quality measurements from lobster cages over a longer period.
- Evaluating the models on temporally separate data from different cages or devices.
- Comparing additional forecasting methods while retaining a simple baseline.
- Assessing alert performance with particular attention to false negatives and warning lead time.
- Validating alert thresholds with aquaculture experts and relevant field data.
- Integrating the selected forecasting workflow into a monitoring dashboard after adequate validation.

## 10. Summary

This experiment establishes a reproducible workflow for 15-minute dissolved oxygen forecasting using synthetic water-quality data. It includes chronological data splitting, XGBoost and Persistence evaluation, low-DO event detection at two thresholds, and verification scripts for the model artifacts and report tables.

The current test results favor Persistence for regression accuracy, while XGBoost provides higher recall at the 4.0 mg/L threshold but lower recall at the 3.0 mg/L threshold. These findings should be treated as preliminary and require validation using real aquaculture data before operational use.
