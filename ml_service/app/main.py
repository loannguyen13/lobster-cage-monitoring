
import logging

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request

from ml_service.app.model_service import (
    DOModelService,
    FORECAST_HORIZON
)

from ml_service.app.schemas import (
    PredictionRequest,
    PredictionResponse
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load model một lần khi FastAPI khởi động.
    """

    logger.info("Loading DO prediction model...")

    app.state.model_service = DOModelService()

    logger.info("DO prediction model loaded successfully.")

    yield

    logger.info("FastAPI application shutting down.")


app = FastAPI(
    title="Lobster Water Quality Prediction API",
    description=(
        "XGBoost inference API for predicting "
        "dissolved oxygen 15 minutes ahead."
    ),
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
def root():

    return {
        "message": "Lobster DO Prediction API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
def health_check(request: Request):

    model_service = getattr(
        request.app.state,
        "model_service",
        None
    )

    if model_service is None:
        raise HTTPException(
            status_code=503,
            detail="Model is not available."
        )

    return {
        "status": "healthy",
        "model_loaded": True
    }


@app.get("/model/info")
def model_info(request: Request):

    model_service = request.app.state.model_service

    return model_service.get_info()


@app.post(
    "/predict",
    response_model=PredictionResponse
)
def predict_do(
    payload: PredictionRequest,
    request: Request
):

    model_service = request.app.state.model_service

    try:

        # Model chỉ nhận sáu features đã được training
        input_data = payload.model_dump()

        predicted_do = model_service.predict(input_data)

        # Thời điểm thực hiện inference
        generated_at = datetime.now(timezone.utc)

        # Thời điểm DO được dự đoán
        forecast_timestamp = (
            payload.timestamp
            + timedelta(minutes=FORECAST_HORIZON)
        )

        return PredictionResponse(
            device_id=payload.device_id,

            source_timestamp=payload.timestamp,
            generated_at=generated_at,
            forecast_timestamp=forecast_timestamp,

            prediction_horizon_minutes=FORECAST_HORIZON,

            current_do=payload.do,
            predicted_do=predicted_do,

            model_name="XGBoost Regressor",
            model_version=model_service.get_info()["model_version"]
        )

    except ValueError as error:

        raise HTTPException(
            status_code=422,
            detail=str(error)
        )

    except Exception:

        logger.exception("DO prediction failed.")

        raise HTTPException(
            status_code=500,
            detail="Internal prediction error."
        )
