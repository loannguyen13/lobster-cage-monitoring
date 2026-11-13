
from pathlib import Path
from math import isfinite

import pandas as pd
from xgboost import XGBRegressor


# Features phải khớp chính xác với lúc training
FEATURES = [
    "temperature",
    "ph",
    "do",
    "salinity",
    "turbidity",
    "chlorophyll_a",
]

FORECAST_HORIZON = 15
MODEL_VERSION = "do-xgboost-15m-v1"


# Xác định project root từ vị trí file hiện tại
PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "results"
    / "selected_horizon_model.json"
)


class DOModelService:
    """
    Load và quản lý XGBoost model phục vụ dự báo DO.
    Model chỉ được load một lần khi FastAPI khởi động.
    """

    def __init__(self):

        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model artifact not found: {MODEL_PATH}"
            )

        self.model = XGBRegressor()

        self.model.load_model(str(MODEL_PATH))

        self._validate_model()

    def _validate_model(self):
        """
        Kiểm tra feature names và model structure.
        """

        booster = self.model.get_booster()

        model_features = booster.feature_names

        if model_features is None:
            raise ValueError(
                "Model artifact does not contain feature names."
            )

        if model_features != FEATURES:
            raise ValueError(
                "Model features do not match the API configuration. "
                f"Expected: {FEATURES}. "
                f"Actual: {model_features}."
            )

        if booster.num_boosted_rounds() != 200:
            raise ValueError(
                "Unexpected number of boosting rounds."
            )

    def predict(self, input_data: dict) -> float:
        """
        Nhận dữ liệu hiện tại và dự đoán DO sau 15 phút.
        """

        # Tạo input theo đúng thứ tự lúc training
        input_row = {
            feature: float(input_data[feature])
            for feature in FEATURES
        }

        # Kiểm tra giá trị hợp lệ
        for feature, value in input_row.items():

            if not isfinite(value):
                raise ValueError(
                    f"Invalid value for feature: {feature}"
                )

        X = pd.DataFrame(
            [input_row],
            columns=FEATURES,
            dtype=float
        )

        prediction = self.model.predict(X)

        predicted_do = float(prediction[0])

        if not isfinite(predicted_do):
            raise ValueError(
                "Model returned an invalid prediction."
            )

        return predicted_do

    def get_info(self) -> dict:
        """
        Thông tin model đang được sử dụng.
        """

        return {
            "model_name": "XGBoost Regressor",
            "model_version": MODEL_VERSION,
            "forecast_target": "do_future_15m",
            "forecast_horizon_minutes": FORECAST_HORIZON,
            "features": FEATURES,
            "boosting_rounds": (
                self.model.get_booster().num_boosted_rounds()
            ),
            "model_file": MODEL_PATH.name
        }
