import importlib.util
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import pytest

from application.backfill import (
    MAX_BACKFILL_DAYS,
    BackfillAbortedError,
    BackfillRangeError,
    BackfillResult,
    backfill,
    date_range,
)
from application.prediction import InsufficientHistoryError, PredictionAlreadyExistsError

DAYS = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)]
SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "backfill_predictions.py"


class FakeConnections:
    def __init__(self) -> None:
        self.opened = 0

    @contextmanager
    def __call__(self):
        self.opened += 1
        yield object()


def make_predict(errors: dict[date, Exception] | None = None):
    calls: list[date] = []

    def predict(connection, target_date):
        calls.append(target_date)
        if errors and target_date in errors:
            raise errors[target_date]
        return {}

    return predict, calls


def load_cli():
    spec = importlib.util.spec_from_file_location("backfill_predictions_cli", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_creates_every_date_in_range_with_one_transaction_each():
    predict, calls = make_predict()
    connections = FakeConnections()

    result = backfill(DAYS, predict, connections)

    assert calls == DAYS
    assert connections.opened == len(DAYS)
    assert result.created == 3
    assert result.skipped_existing == 0
    assert result.skipped_insufficient_history == 0


def test_skips_existing_dates_and_continues():
    predict, calls = make_predict({DAYS[1]: PredictionAlreadyExistsError()})

    result = backfill(DAYS, predict, FakeConnections())

    assert calls == DAYS
    assert (result.created, result.skipped_existing) == (2, 1)
    assert result.skipped_dates == [DAYS[1]]


def test_skips_insufficient_history_dates_and_continues():
    predict, calls = make_predict({DAYS[0]: InsufficientHistoryError("missing lag")})

    result = backfill(DAYS, predict, FakeConnections())

    assert calls == DAYS
    assert (result.created, result.skipped_insufficient_history) == (2, 1)


def test_unexpected_error_stops_and_reports_the_date():
    boom = RuntimeError("boom")
    predict, calls = make_predict({DAYS[1]: boom})

    with pytest.raises(BackfillAbortedError) as excinfo:
        backfill(DAYS, predict, FakeConnections())

    assert excinfo.value.target_date == DAYS[1]
    assert excinfo.value.__cause__ is boom
    assert excinfo.value.result.created == 1
    assert calls == DAYS[:2]


def test_date_range_is_inclusive():
    assert date_range(DAYS[0], DAYS[2]) == DAYS
    assert date_range(DAYS[0], DAYS[0]) == [DAYS[0]]


def test_date_range_rejects_start_after_end():
    with pytest.raises(BackfillRangeError):
        date_range(DAYS[2], DAYS[0])


def test_date_range_rejects_more_than_the_maximum_days():
    start = date(2023, 1, 1)
    assert len(date_range(start, start + timedelta(days=MAX_BACKFILL_DAYS - 1))) == (
        MAX_BACKFILL_DAYS
    )
    with pytest.raises(BackfillRangeError):
        date_range(start, start + timedelta(days=MAX_BACKFILL_DAYS))


def test_dry_run_lists_dates_without_touching_model_or_database(monkeypatch, capsys):
    module = load_cli()

    def forbidden(*args, **kwargs):
        raise AssertionError("dry run must not touch the database or the model")

    monkeypatch.setattr(module, "create_database_engine", forbidden)
    monkeypatch.setattr(module, "PredictionService", forbidden)

    code = module.main(["--start", "2023-01-01", "--end", "2023-01-03", "--dry-run"])

    assert code == 0
    output = capsys.readouterr().out
    assert "2023-01-01" in output
    assert "2023-01-03" in output
    assert "3 dates" in output


def test_cli_rejects_invalid_range(capsys):
    module = load_cli()

    code = module.main(["--start", "2023-02-01", "--end", "2023-01-01", "--dry-run"])

    assert code == 2
    assert "Invalid range" in capsys.readouterr().err


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def begin(self):
        raise AssertionError("no transaction expected")

    def dispose(self) -> None:
        self.disposed = True


ARGS = ["--start", "2023-01-01", "--end", "2023-01-02"]


def test_cli_reports_engine_setup_failure(monkeypatch, capsys):
    module = load_cli()

    def broken_engine():
        raise RuntimeError("DATABASE_URL missing")

    monkeypatch.setattr(module, "create_database_engine", broken_engine)

    assert module.main(ARGS) == 1
    assert "setup failed" in capsys.readouterr().err


def test_cli_reports_service_setup_failure_and_disposes_engine(monkeypatch, capsys):
    module = load_cli()
    engine = FakeEngine()

    def broken_service():
        raise RuntimeError("model artifact unavailable")

    monkeypatch.setattr(module, "create_database_engine", lambda: engine)
    monkeypatch.setattr(module, "PredictionService", broken_service)

    assert module.main(ARGS) == 1
    assert "setup failed" in capsys.readouterr().err
    assert engine.disposed


def test_cli_reports_aborted_backfill_and_disposes_engine(monkeypatch, capsys):
    module = load_cli()
    engine = FakeEngine()

    class FakeService:
        def predict(self, connection, target_date):
            return {}

    def aborting_backfill(dates, predict, connections):
        raise BackfillAbortedError(date(2023, 1, 2), BackfillResult(created=1)) from ValueError(
            "boom"
        )

    monkeypatch.setattr(module, "create_database_engine", lambda: engine)
    monkeypatch.setattr(module, "PredictionService", FakeService)
    monkeypatch.setattr(module, "backfill", aborting_backfill)

    assert module.main(ARGS) == 1
    err = capsys.readouterr().err
    assert "2023-01-02" in err
    assert "created=1" in err
    assert engine.disposed


class FakeModels:
    def __init__(self, versions: set[str]) -> None:
        self.versions = versions

    def get_by_version(self, connection, version):
        return {"version": version} if version in self.versions else None


class ConnectableEngine(FakeEngine):
    def connect(self):
        @contextmanager
        def manager():
            yield object()

        return manager()


def test_cli_fails_when_the_requested_model_version_is_not_registered(monkeypatch, capsys):
    module = load_cli()
    engine = ConnectableEngine()
    monkeypatch.setattr(module, "create_database_engine", lambda: engine)
    monkeypatch.setattr(module, "PredictionService", lambda: type("S", (), {"predict": None})())
    monkeypatch.setattr(module, "ModelRepository", lambda: FakeModels({"1.1.0"}))
    monkeypatch.setattr(module, "backfill", lambda *args: pytest.fail("must not backfill"))

    assert module.main([*ARGS, "--model-version", "1.2.0"]) == 1
    assert "1.2.0 is not registered" in capsys.readouterr().err
    assert engine.disposed


def test_cli_predicts_with_the_requested_registered_version(monkeypatch, capsys):
    module = load_cli()
    engine = ConnectableEngine()
    calls: list[tuple[date, str | None]] = []

    class FakeService:
        def predict(self, connection, target_date, model_version=None):
            calls.append((target_date, model_version))
            return {}

    def fake_backfill(dates, predict, connections):
        for target_date in dates:
            predict(object(), target_date)
        return BackfillResult(created=len(dates))

    monkeypatch.setattr(module, "create_database_engine", lambda: engine)
    monkeypatch.setattr(module, "PredictionService", FakeService)
    monkeypatch.setattr(module, "ModelRepository", lambda: FakeModels({"1.2.0"}))
    monkeypatch.setattr(module, "backfill", fake_backfill)

    assert module.main([*ARGS, "--model-version", "1.2.0"]) == 0
    assert calls == [(date(2023, 1, 1), "1.2.0"), (date(2023, 1, 2), "1.2.0")]


def test_cli_without_a_version_predicts_with_the_active_model(monkeypatch):
    module = load_cli()
    engine = ConnectableEngine()
    calls: list[tuple[date, str | None]] = []

    class FakeService:
        def predict(self, connection, target_date, model_version=None):
            calls.append((target_date, model_version))
            return {}

    def fake_backfill(dates, predict, connections):
        predict(object(), dates[0])
        return BackfillResult(created=1)

    monkeypatch.setattr(module, "create_database_engine", lambda: engine)
    monkeypatch.setattr(module, "PredictionService", FakeService)
    monkeypatch.setattr(module, "ModelRepository", lambda: pytest.fail("no version lookup"))
    monkeypatch.setattr(module, "backfill", fake_backfill)

    assert module.main(ARGS) == 0
    assert calls == [(date(2023, 1, 1), None)]
