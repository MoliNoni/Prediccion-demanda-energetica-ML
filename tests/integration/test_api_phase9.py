from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from api.dependencies import get_connection, get_prediction_service
from api.main import app
from application.prediction import PredictionService
from database.repositories import ModelRepository
from database.schema import metadata
from models.serving import MlflowModelLoader

HISTORICAL_PATH = Path("data/interim/energy_demand_daily.parquet")


@pytest.fixture
def phase9_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(engine)

    def connection_override():
        with engine.begin() as connection:
            yield connection

    app.dependency_overrides[get_connection] = connection_override
    app.dependency_overrides[get_prediction_service] = lambda: PredictionService(
        history_path=HISTORICAL_PATH,
        model_loader=MlflowModelLoader(),
    )
    with TestClient(app) as client:
        yield client, engine
    app.dependency_overrides.clear()


def create_active_model(engine: Engine, *, name: str = "HistGradientBoostingRegressor") -> None:
    with engine.begin() as connection:
        ModelRepository().create(
            connection,
            name=name,
            version="1.0.0",
            horizon=1,
            is_active=True,
        )


def test_prediction_is_generated_and_persisted(phase9_client) -> None:
    client, engine = phase9_client
    create_active_model(engine)

    response = client.post("/api/v1/predictions", json={"target_date": "2023-01-02"})

    assert response.status_code == 201
    body = response.json()
    assert body["target_date"] == "2023-01-02"
    assert isinstance(body["predicted_demand_kwh"], float)
    assert body["actual_demand_kwh"] is not None
    assert body["model_name"] == "HistGradientBoostingRegressor"
    assert body["model_version"] == "1.0.0"
    assert body["horizon"] == 1
    with engine.connect() as connection:
        table = metadata.tables["energy_predictions"]
        assert connection.execute(select(func.count()).select_from(table)).scalar_one() == 1


def test_duplicate_prediction_returns_conflict(phase9_client) -> None:
    client, engine = phase9_client
    create_active_model(engine)

    assert client.post("/api/v1/predictions", json={"target_date": "2023-01-02"}).status_code == 201
    response = client.post("/api/v1/predictions", json={"target_date": "2023-01-02"})

    assert response.status_code == 409


def test_no_active_model_returns_not_found(phase9_client) -> None:
    client, _ = phase9_client

    response = client.post("/api/v1/predictions", json={"target_date": "2023-01-02"})

    assert response.status_code == 404


def test_multiple_active_models_returns_internal_error(phase9_client) -> None:
    client, engine = phase9_client
    create_active_model(engine)
    create_active_model(engine, name="other")

    response = client.post("/api/v1/predictions", json={"target_date": "2023-01-02"})

    assert response.status_code == 500


def test_incomplete_history_returns_service_unavailable(phase9_client) -> None:
    client, engine = phase9_client
    create_active_model(engine)

    response = client.post("/api/v1/predictions", json={"target_date": "2016-01-01"})

    assert response.status_code == 503
    assert "historical demand is incomplete" in response.json()["detail"]


def test_missing_actual_is_returned_as_null(phase9_client) -> None:
    client, engine = phase9_client
    create_active_model(engine)

    response = client.post("/api/v1/predictions", json={"target_date": "2015-12-31"})

    assert response.status_code == 201
    assert response.json()["actual_demand_kwh"] is None
