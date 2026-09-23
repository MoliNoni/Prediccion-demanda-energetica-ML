import pytest

from evaluation.metrics import mae, rmse, smape, wape


def test_mae() -> None:
    assert mae([1, 2, 3], [2, 2, 5]) == pytest.approx(1.0)


def test_rmse() -> None:
    assert rmse([1, 2, 3], [2, 2, 5]) == pytest.approx((5 / 3) ** 0.5)


def test_smape() -> None:
    assert smape([100, 100], [110, 90]) == pytest.approx(10.0250626566)


def test_wape() -> None:
    assert wape([100, 100], [110, 90]) == pytest.approx(10.0)


def test_zero_denominators_are_safe() -> None:
    assert smape([0, 0], [0, 0]) == 0.0
    assert wape([0, 0], [0, 0]) == 0.0
