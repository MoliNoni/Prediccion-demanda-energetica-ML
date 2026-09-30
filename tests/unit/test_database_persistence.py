import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, insert
from sqlalchemy.exc import IntegrityError

from config import Settings
from database.repositories import EnergyPredictionRepository, ModelRepository
from database.schema import energy_predictions_table, metadata
from database.session import create_database_engine


@pytest.fixture
def connection():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        if isinstance(dbapi_connection, sqlite3.Connection):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    metadata.create_all(engine)
    with engine.begin() as transaction:
        yield transaction


def test_database_url_is_required_from_environment(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@host/database")
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_database_engine_uses_psycopg3_dialect(monkeypatch) -> None:
    monkeypatch.setattr(
        "database.session.get_settings",
        lambda: Settings(
            _env_file=None,
            DATABASE_URL="postgresql://user:pass@host/database",
        ),
    )

    engine = create_database_engine()

    assert engine.url.drivername == "postgresql+psycopg"


def test_repositories_insert_and_query_operational_records(connection) -> None:
    models = ModelRepository()
    predictions = EnergyPredictionRepository()
    model_id = models.create(
        connection,
        name="HistGradientBoostingRegressor",
        version="0.1.0",
        horizon=1,
        is_active=True,
    )
    prediction_id = predictions.create(
        connection,
        target_date=date(2023, 12, 31),
        predicted_demand_kwh=100.0,
        actual_demand_kwh=None,
        model_id=model_id,
    )

    assert models.get(connection, model_id)["is_active"] is True
    prediction = predictions.get(connection, prediction_id)
    assert prediction["model_id"] == model_id
    assert prediction["actual_demand_kwh"] is None


def test_prediction_integrity_constraints(connection) -> None:
    predictions = EnergyPredictionRepository()
    model_id = ModelRepository().create(
        connection,
        name="baseline",
        version="0.1.0",
        horizon=1,
    )
    predictions.create(
        connection,
        target_date=date(2023, 12, 31),
        predicted_demand_kwh=100.0,
        actual_demand_kwh=None,
        model_id=model_id,
    )

    with pytest.raises(IntegrityError):
        predictions.create(
            connection,
            target_date=date(2023, 12, 31),
            predicted_demand_kwh=101.0,
            actual_demand_kwh=None,
            model_id=model_id,
        )


def test_prediction_requires_an_existing_model(connection) -> None:
    with pytest.raises(IntegrityError):
        EnergyPredictionRepository().create(
            connection,
            target_date=date(2023, 12, 31),
            predicted_demand_kwh=100.0,
            actual_demand_kwh=None,
            model_id=uuid4(),
        )


def test_promotion_keeps_one_active_model_and_preserves_prediction_lineage(connection) -> None:
    models = ModelRepository()
    predictions = EnergyPredictionRepository()
    v1_id = models.create(
        connection,
        name="HistGradientBoostingRegressor",
        version="1.0.0",
        horizon=1,
        is_active=True,
    )
    predictions.create(
        connection,
        target_date=date(2023, 12, 31),
        predicted_demand_kwh=100.0,
        actual_demand_kwh=None,
        model_id=v1_id,
    )
    v2_id = models.create(
        connection,
        name="HistGradientBoostingRegressor",
        version="1.1.0",
        horizon=1,
    )

    models.promote(connection, v2_id)

    assert [model["id"] for model in models.get_active(connection)] == [v2_id]
    assert predictions.list(connection, start_date=None, end_date=None, page=1, page_size=10)[0][0][
        "model_id"
    ] == v1_id
    models.promote(connection, v1_id)
    assert [model["id"] for model in models.get_active(connection)] == [v1_id]


def test_prediction_list_orders_by_target_date_or_newest_generated(connection) -> None:
    model_id = ModelRepository().create(
        connection, name="baseline", version="1.0.0", horizon=1, is_active=True
    )
    for target, created in [
        (date(2010, 1, 1), datetime(2026, 1, 3, tzinfo=UTC)),
        (date(2023, 1, 1), datetime(2026, 1, 1, tzinfo=UTC)),
        (date(2023, 1, 2), datetime(2026, 1, 1, tzinfo=UTC)),
    ]:
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
    predictions = EnergyPredictionRepository()
    window = {"start_date": None, "end_date": None, "page": 1, "page_size": 10}

    default, _ = predictions.list(connection, **window)
    newest, total = predictions.list(connection, **window, order="created_desc")

    assert [row["target_date"] for row in default] == [
        date(2010, 1, 1),
        date(2023, 1, 1),
        date(2023, 1, 2),
    ]
    assert [row["target_date"] for row in newest] == [
        date(2010, 1, 1),
        date(2023, 1, 2),
        date(2023, 1, 1),
    ]
    assert total == 3


def test_migration_contains_approved_physical_contract() -> None:
    migration = Path("migrations/001_create_operational_tables.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE models" in migration
    assert "horizon INTEGER NOT NULL" in migration
    assert "CREATE TABLE energy_predictions" in migration
    assert "model_id UUID NOT NULL REFERENCES models(id)" in migration
    assert "UNIQUE (target_date, model_id)" in migration


def test_single_active_model_migration_is_present() -> None:
    migration = Path("migrations/002_enforce_single_active_model.sql").read_text(encoding="utf-8")

    assert "CREATE UNIQUE INDEX uq_models_single_active" in migration
    assert "WHERE is_active = true" in migration
