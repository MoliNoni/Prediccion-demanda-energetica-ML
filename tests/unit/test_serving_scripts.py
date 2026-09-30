import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from database.repositories import ModelRepository
from database.schema import metadata
from models.serving_registry import SUPPORTED_SERVING_MODELS

SCRIPTS = Path(__file__).parents[2] / "scripts"
NAME = "HistGradientBoostingRegressor"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_cli", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeLoader:
    def load(self):
        return object(), {}


@pytest.fixture
def engine(tmp_path):
    database = create_engine(f"sqlite+pysqlite:///{tmp_path / 'models.db'}")
    metadata.create_all(database)
    return database


def bind_script(module, engine, monkeypatch) -> None:
    monkeypatch.setattr(module, "create_database_engine", lambda: engine)
    for version, (name, horizon, _) in SUPPORTED_SERVING_MODELS.items():
        monkeypatch.setitem(SUPPORTED_SERVING_MODELS, version, (name, horizon, FakeLoader))


def seed_active_v1_1_0(engine):
    with engine.begin() as connection:
        return ModelRepository().create(
            connection, name=NAME, version="1.1.0", horizon=1, is_active=True
        )


def rows(engine) -> dict[str, bool]:
    with engine.connect() as connection:
        from database.schema import models_table

        return {row.version: row.is_active for row in connection.execute(models_table.select())}


def test_registering_1_2_0_inactive_is_a_dry_run_by_default(engine, monkeypatch) -> None:
    module = load_script("register_serving_model")
    bind_script(module, engine, monkeypatch)
    seed_active_v1_1_0(engine)

    assert module.register_inactive_model("1.2.0") == (None, False)

    assert rows(engine) == {"1.1.0": True}


def test_registering_1_2_0_inactive_inserts_it_once_and_keeps_the_active_model(
    engine, monkeypatch
) -> None:
    module = load_script("register_serving_model")
    bind_script(module, engine, monkeypatch)
    seed_active_v1_1_0(engine)

    model_id, created = module.register_inactive_model("1.2.0", execute=True)
    repeated_id, repeated_created = module.register_inactive_model("1.2.0", execute=True)

    assert created and not repeated_created
    assert repeated_id == model_id
    assert rows(engine) == {"1.1.0": True, "1.2.0": False}


def test_registering_rejects_unsupported_versions(engine, monkeypatch) -> None:
    module = load_script("register_serving_model")
    bind_script(module, engine, monkeypatch)

    with pytest.raises(ValueError, match="Unsupported"):
        module.register_inactive_model("9.9.9", execute=True)


def test_promoting_1_2_0_validates_by_default_and_swaps_the_active_model_on_execute(
    engine, monkeypatch
) -> None:
    register = load_script("register_serving_model")
    promote = load_script("promote_serving_model")
    bind_script(register, engine, monkeypatch)
    bind_script(promote, engine, monkeypatch)
    seed_active_v1_1_0(engine)
    model_id, _ = register.register_inactive_model("1.2.0", execute=True)

    assert promote.promote_serving_model("1.2.0") == model_id
    assert rows(engine) == {"1.1.0": True, "1.2.0": False}

    assert promote.promote_serving_model("1.2.0", execute=True) == model_id
    assert rows(engine) == {"1.1.0": False, "1.2.0": True}


def test_promoting_an_unregistered_1_2_0_fails(engine, monkeypatch) -> None:
    promote = load_script("promote_serving_model")
    bind_script(promote, engine, monkeypatch)

    with pytest.raises(ValueError, match="missing"):
        promote.promote_serving_model("1.2.0")


def test_promote_cli_supports_1_2_0() -> None:
    assert "1.2.0" in load_script("promote_serving_model").SUPPORTED_MODELS
