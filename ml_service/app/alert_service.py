
from math import isfinite


# Alert thresholds (mg/L)
WARNING_THRESHOLD = 4.0
CRITICAL_THRESHOLD = 3.0


def evaluate_do_alert(predicted_do: float):
    """
    Evaluate predicted dissolved oxygen and classify alert severity.

    Rules:
        DO >= 4.0       -> No alert
        3.0 <= DO < 4.0 -> WARNING
        DO < 3.0        -> CRITICAL

    Returns:
        dict: Alert information if a threshold is violated.
        None: If predicted DO is within the normal range.
    """

    try:
        predicted_do = float(predicted_do)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Predicted DO must be a valid numeric value."
        ) from error

    if not isfinite(predicted_do):
        raise ValueError(
            "Predicted DO must be a finite number."
        )

    if predicted_do < CRITICAL_THRESHOLD:
        return {
            "alert_type": "PREDICTED_LOW_DO",
            "severity": "CRITICAL",
            "threshold": CRITICAL_THRESHOLD,
            "predicted_do": predicted_do,
            "unit": "mg/L",
            "message": (
                f"Critical warning: predicted DO is "
                f"{predicted_do:.2f} mg/L, below "
                f"{CRITICAL_THRESHOLD:.1f} mg/L."
            )
        }

    if predicted_do < WARNING_THRESHOLD:
        return {
            "alert_type": "PREDICTED_LOW_DO",
            "severity": "WARNING",
            "threshold": WARNING_THRESHOLD,
            "predicted_do": predicted_do,
            "unit": "mg/L",
            "message": (
                f"Low DO warning: predicted DO is "
                f"{predicted_do:.2f} mg/L, below "
                f"{WARNING_THRESHOLD:.1f} mg/L."
            )
        }

    return None
