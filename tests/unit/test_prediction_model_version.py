from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine

from application.prediction import ModelNotRegisteredError, PredictionService
from database.repositories import EnergyPredictionRepository, ModelRepository
from database.schema import metadata
from ingestion.constants import EXPECTED_COLUMNS
from ingestion.constants import TARGET_COLUMN as DEMAND_COLUMN

NAME = "HistGradientBoostingRegressor"
TARGET = date(2023, 1, 10)


class ConstantModel:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.full(len(frame), self.value)


class FakeRegistry:
    def __init__(self) -> None:
        self.loaded_versions: list[str] = []

    def load(self, active_model):
        version = str(active_model["version"])
        self.loaded_versions.append(version)
        value = {"1.1.0": 100.0, "1.2.0": 200.0}[version]
        return (
            ConstantModel(value),
            {"predictor_columns": ["x"]},
            lambda frame, target_date: pd.DataFrame({"x": [1.0]}),
        )


@pytest.fixture
def connection():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as transaction:
        yield transaction


@pytest.fixture
def service(tmp_path):
    dates = pd.date_range("2023-01-01", "2023-01-31", freq="D")
    history = pd.DataFrame(0.0, index=range(len(dates)), columns=list(EXPECTED_COLUMNS))
    history["Fecha"] = dates
    history[DEMAND_COLUMN] = 150.0
    path = tmp_path / "history.parquet"
    history.to_parquet(path, index=False)
    registry = FakeRegistry()
    return PredictionService(history_path=path, serving_registry=registry), registry


def register_models(connection) -> tuple[object, object]:
    models = ModelRepository()
    active = models.create(connection, name=NAME, version="1.1.0", horizon=1, is_active=True)
    inactive = models.create(connection, name=NAME, version="1.2.0", horizon=1)
    return active, inactive


def test_default_prediction_uses_the_active_model(connection, service) -> None:
    active_id, _ = register_models(connection)
    prediction_service, registry = service

    result = prediction_service.predict(connection, TARGET)

    assert registry.loaded_versions == ["1.1.0"]
    assert result["model_id"] == active_id
    assert result["predicted_demand_kwh"] == pytest.approx(100.0)


def test_prediction_with_a_version_uses_that_registered_model_and_keeps_the_active_one(
    connection, service
) -> None:
    _, inactive_id = register_models(connection)
    prediction_service, registry = service

    result = prediction_service.predict(connection, TARGET, model_version="1.2.0")

    assert registry.loaded_versions == ["1.2.0"]
    assert result["model_id"] == inactive_id
    assert result["model_version"] == "1.2.0"
    assert result["predicted_demand_kwh"] == pytest.approx(200.0)
    assert [model["version"] for model in ModelRepository().get_active(connection)] == ["1.1.0"]
    stored = EnergyPredictionRepository().get(connection, result["id"])
    assert stored["model_id"] == inactive_id


def test_prediction_with_an_unregistered_version_fails_clearly(connection, service) -> None:
    register_models(connection)
    prediction_service, registry = service

    with pytest.raises(ModelNotRegisteredError, match="9.9.9"):
        prediction_service.predict(connection, TARGET, model_version="9.9.9")
    assert registry.loaded_versions == []


def test_get_by_version_returns_the_row_or_none(connection) -> None:
    _, inactive_id = register_models(connection)

    assert ModelRepository().get_by_version(connection, "1.2.0")["id"] == inactive_id
    assert ModelRepository().get_by_version(connection, "0.0.0") is None
