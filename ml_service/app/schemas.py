
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PredictionRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid"
    )

    device_id: str = Field(
        min_length=1,
        max_length=100
    )

    timestamp: datetime

    temperature: float = Field(allow_inf_nan=False)
    ph: float = Field(allow_inf_nan=False)
    do: float = Field(allow_inf_nan=False)
    salinity: float = Field(allow_inf_nan=False)
    turbidity: float = Field(allow_inf_nan=False)
    chlorophyll_a: float = Field(allow_inf_nan=False)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value):

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Timestamp must include timezone information."
            )

        return value


class PredictionResponse(BaseModel):

    device_id: str

    source_timestamp: datetime
    generated_at: datetime
    forecast_timestamp: datetime

    prediction_horizon_minutes: int

    current_do: float
    predicted_do: float

    unit: str = "mg/L"

    model_name: str
    model_version: str
