from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from api.dependencies import get_connection, get_historical_demand_query, get_prediction_service
from api.main import app
from application.historical_demand import HistoricalDemandQuery
from application.prediction import PredictionService
from database.repositories import EnergyPredictionRepository, ModelRepository
from database.schema import energy_predictions_table, metadata
from models.serving import MlflowModelLoader


@pytest.fixture
def api_client(tmp_path: Path):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(engine)
    demand_path = tmp_path / "demand.parquet"
    pd.DataFrame(
        {
            "Fecha": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]),
            "Demanda Energia SIN kWh": [100.0, 200.0, 300.0],
        }
    ).to_parquet(demand_path, index=False)

    def connection_override():
        with engine.begin() as connection:
            yield connection

    app.dependency_overrides[get_connection] = connection_override
    app.dependency_overrides[get_historical_demand_query] = lambda: HistoricalDemandQuery(
        demand_path
    )
    with TestClient(app) as client:
        yield client, engine, tmp_path
    app.dependency_overrides.clear()


def create_model(engine: Engine, *, active: bool = False):
    with engine.begin() as connection:
        return ModelRepository().create(
            connection,
            name="HistGradientBoostingRegressor",
            version="0.1.0" if active else "0.2.0",
            horizon=1,
            is_active=active,
        )


def test_health_contract(api_client) -> None:
    client, _, _ = api_client

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_active_model_responses(api_client) -> None:
    client, engine, _ = api_client
    assert client.get("/api/v1/models/active").status_code == 404

    model_id = create_model(engine, active=True)
    response = client.get("/api/v1/models/active")

    assert response.status_code == 200
    assert response.json()["id"] == str(model_id)
    assert response.json()["is_active"] is True


def test_multiple_active_models_return_integrity_error(api_client) -> None:
    client, engine, _ = api_client
    create_model(engine, active=True)
    with engine.begin() as connection:
        ModelRepository().create(
            connection,
            name="baseline",
            version="0.1.0",
            horizon=1,
            is_active=True,
        )

    response = client.get("/api/v1/models/active")

    assert response.status_code == 500


def test_prediction_listing_filters_pagination_and_null_actual(api_client) -> None:
    client, engine, _ = api_client
    model_id = create_model(engine)
    with engine.begin() as connection:
        predictions = EnergyPredictionRepository()
        predictions.create(
            connection,
            target_date=date(2023, 1, 1),
            predicted_demand_kwh=100.0,
            actual_demand_kwh=None,
            model_id=model_id,
        )
        predictions.create(
            connection,
            target_date=date(2023, 1, 2),
            predicted_demand_kwh=200.0,
            actual_demand_kwh=201.0,
            model_id=model_id,
        )

    response = client.get("/api/v1/predictions?page_size=1&page=2")
    filtered = client.get("/api/v1/predictions?start_date=2023-01-02&end_date=2023-01-02")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["items"][0]["target_date"] == "2023-01-02"
    assert filtered.json()["items"][0]["actual_demand_kwh"] == 201.0
    assert (
        client.get("/api/v1/predictions?start_date=2023-01-03&end_date=2023-01-02").status_code
        == 422
    )
    assert client.get("/api/v1/predictions?page=0").status_code == 422
    assert client.get("/api/v1/predictions").json()["items"] != []


def test_prediction_listing_order_option(api_client) -> None:
    client, engine, _ = api_client
    model_id = create_model(engine)
    rows = [
        (date(2010, 1, 1), datetime(2026, 1, 3, tzinfo=UTC)),
        (date(2023, 1, 2), datetime(2026, 1, 1, tzinfo=UTC)),
        (date(2023, 1, 1), datetime(2026, 1, 1, tzinfo=UTC)),
    ]
    with engine.begin() as connection:
        for target, created in rows:
            connection.execute(
                insert(energy_predictions_table).values(
                    id=uuid4(),
                    target_date=target,
                    predicted_demand_kwh=1.0,
                    actual_demand_kwh=None,
                    model_id=model_id,
                    created_at=created,
                )
            )

    default = client.get("/api/v1/predictions").json()["items"]
    newest = client.get("/api/v1/predictions?order=created_desc").json()["items"]
    paged = client.get("/api/v1/predictions?order=created_desc&page_size=1&page=2").json()
    filtered = client.get(
        "/api/v1/predictions?order=created_desc&start_date=2023-01-01&end_date=2023-12-31"
    ).json()

    assert [item["target_date"] for item in default] == ["2010-01-01", "2023-01-01", "2023-01-02"]
    assert [item["target_date"] for item in newest] == ["2010-01-01", "2023-01-02", "2023-01-01"]
    assert paged["total"] == 3
    assert paged["items"][0]["target_date"] == "2023-01-02"
    assert [item["target_date"] for item in filtered["items"]] == ["2023-01-02", "2023-01-01"]
    assert client.get("/api/v1/predictions?order=bogus").status_code == 422


def test_prediction_listing_returns_empty_list(api_client) -> None:
    client, _, _ = api_client

    response = client.get("/api/v1/predictions")

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 1, "page_size": 30, "total": 0}


def test_demand_listing_filters_pagination_and_failures(api_client) -> None:
    client, _, tmp_path = api_client
    response = client.get("/api/v1/demand?page_size=1&page=2")
    filtered = client.get("/api/v1/demand?start_date=2023-01-03&end_date=2023-01-03")

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert response.json()["items"][0] == {"date": "2023-01-02", "demand_kwh": 200.0}
    assert filtered.json()["items"] == [{"date": "2023-01-03", "demand_kwh": 300.0}]
    assert client.get("/api/v1/demand?start_date=2023-01-03&end_date=2023-01-02").status_code == 422
    assert client.get("/api/v1/demand?start_date=2024-01-01").json()["items"] == []

    missing_path = tmp_path / "missing.parquet"
    app.dependency_overrides[get_historical_demand_query] = lambda: HistoricalDemandQuery(
        missing_path
    )
    assert client.get("/api/v1/demand").status_code == 500


def test_prediction_post_is_unavailable_without_model_artifact(api_client) -> None:
    client, engine, tmp_path = api_client
    create_model(engine, active=True)
    app.dependency_overrides[get_prediction_service] = lambda: PredictionService(
        history_path=tmp_path / "missing.parquet",
        model_loader=MlflowModelLoader(tmp_path / "missing-model.json"),
    )

    response = client.post("/api/v1/predictions", json={"target_date": "2023-01-02"})

    assert response.status_code == 503
    assert "no serialized model artifact" in response.json()["detail"]
    assert client.post("/api/v1/predictions", json={}).status_code == 422
