
import pytest

from ml_service.app.alert_service import evaluate_do_alert


@pytest.mark.parametrize(
    "predicted_do",
    [4.0, 4.5, 5.0, 8.0]
)
def test_normal_do(predicted_do):

    result = evaluate_do_alert(predicted_do)

    assert result is None


@pytest.mark.parametrize(
    "predicted_do",
    [3.9, 3.5, 3.1, 3.0]
)
def test_warning_do(predicted_do):

    result = evaluate_do_alert(predicted_do)

    assert result is not None
    assert result["severity"] == "WARNING"
    assert result["threshold"] == 4.0
    assert result["alert_type"] == "PREDICTED_LOW_DO"


@pytest.mark.parametrize(
    "predicted_do",
    [2.9, 2.5, 1.0, 0.0]
)
def test_critical_do(predicted_do):

    result = evaluate_do_alert(predicted_do)

    assert result is not None
    assert result["severity"] == "CRITICAL"
    assert result["threshold"] == 3.0
    assert result["alert_type"] == "PREDICTED_LOW_DO"


@pytest.mark.parametrize(
    "invalid_value",
    [float("nan"), float("inf"), float("-inf")]
)
def test_invalid_non_finite_values(invalid_value):

    with pytest.raises(ValueError):
        evaluate_do_alert(invalid_value)


@pytest.mark.parametrize(
    "invalid_value",
    [None, "invalid"]
)
def test_invalid_input_type(invalid_value):

    with pytest.raises(ValueError):
        evaluate_do_alert(invalid_value)


def test_alert_message_contains_prediction():

    result = evaluate_do_alert(2.8)

    assert result["severity"] == "CRITICAL"
    assert "2.80 mg/L" in result["message"]
