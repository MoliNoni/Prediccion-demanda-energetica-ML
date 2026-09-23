from collections.abc import Sequence

import numpy as np


def _arrays(actual: Sequence[float], predicted: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    if actual_array.shape != predicted_array.shape:
        raise ValueError("actual and predicted must have the same shape")
    if not np.isfinite(actual_array).all() or not np.isfinite(predicted_array).all():
        raise ValueError("actual and predicted must contain only finite values")
    return actual_array, predicted_array


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    actual_array, predicted_array = _arrays(actual, predicted)
    return float(np.mean(np.abs(actual_array - predicted_array)))


def rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    actual_array, predicted_array = _arrays(actual, predicted)
    return float(np.sqrt(np.mean(np.square(actual_array - predicted_array))))


def smape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    actual_array, predicted_array = _arrays(actual, predicted)
    denominator = np.abs(actual_array) + np.abs(predicted_array)
    terms = np.divide(
        2 * np.abs(actual_array - predicted_array),
        denominator,
        out=np.zeros_like(denominator),
        where=denominator != 0,
    )
    return float(np.mean(terms) * 100)


def wape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    actual_array, predicted_array = _arrays(actual, predicted)
    denominator = np.sum(np.abs(actual_array))
    if denominator == 0:
        return 0.0
    return float(np.sum(np.abs(actual_array - predicted_array)) / denominator * 100)
