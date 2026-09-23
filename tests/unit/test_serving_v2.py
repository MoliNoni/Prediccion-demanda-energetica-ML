import json

import pandas as pd
import pytest

from features.contracts import FEATURE_CONTRACT_V2
from models.serving_v2 import (
    MODEL_NAME_V2,
    MODEL_VERSION_V2,
    CandidateMlflowModelLoaderV2,
    CandidateServingArtifactUnavailableError,
    predict_candidate_v2,
)


def candidate_metadata() -> dict[str, object]:
    return {
        "model_name": MODEL_NAME_V2,
        "model_version": MODEL_VERSION_V2,
        "feature_set_version": FEATURE_CONTRACT_V2.version,
        "predictor_columns": list(FEATURE_CONTRACT_V2.predictor_columns),
        "candidate": True,
        "promotion_status": "not_promoted",
        "tracking_uri": "file:///unused-for-test",
        "model_uri": "runs:/candidate/model",
    }


def test_candidate_loader_accepts_only_the_v2_non_promoted_contract(tmp_path, monkeypatch) -> None:
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate_metadata()), encoding="utf-8")
    expected_model = object()
    monkeypatch.setattr("models.serving_v2.mlflow.sklearn.load_model", lambda _: expected_model)

    model, metadata = CandidateMlflowModelLoaderV2(path).load()

    assert model is expected_model
    assert metadata["promotion_status"] == "not_promoted"


def test_candidate_loader_rejects_a_feature_contract_mismatch(tmp_path) -> None:
    metadata = candidate_metadata()
    metadata["predictor_columns"] = ["lag_1"]
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(CandidateServingArtifactUnavailableError, match="metadata is invalid"):
        CandidateMlflowModelLoaderV2(path).load()


def test_candidate_loader_prefers_runtime_tracking_uri_over_stale_windows_path(
    tmp_path, monkeypatch
) -> None:
    metadata = candidate_metadata()
    metadata["tracking_uri"] = "file:///C:/Users/User/Desktop/project/mlruns"
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "file:///app/mlruns")

    captured: list[str] = []

    def fake_set_tracking_uri(value: str) -> None:
        captured.append(value)

    def fake_load_model(model_uri: str):
        assert captured[-1] == "file:///app/mlruns"
        assert model_uri == "runs:/candidate/model"
        return object()

    monkeypatch.setattr("models.serving_v2.mlflow.set_tracking_uri", fake_set_tracking_uri)
    monkeypatch.setattr("models.serving_v2.mlflow.sklearn.load_model", fake_load_model)

    model, metadata = CandidateMlflowModelLoaderV2(path).load()

    assert model is not None
    assert metadata["tracking_uri"] == "file:///app/mlruns"


def test_candidate_prediction_uses_metadata_feature_order(monkeypatch) -> None:
    dates = pd.date_range("2023-01-01", periods=40, freq="D")
    frame = pd.DataFrame(
        {
            "Fecha": dates,
            "Demanda Energia SIN kWh": range(40),
            "Generación kWh": range(40),
            "Demanda No Atendida kWh": [None] * len(dates),
            "Exportaciones kWh": [None] * len(dates),
            "Importaciones kWh": [None] * len(dates),
        }
    )

    class Model:
        def predict(self, values):
            assert values.columns.tolist() == list(FEATURE_CONTRACT_V2.predictor_columns)
            return [123.0]

    class Loader:
        def load(self):
            return Model(), candidate_metadata()

    monkeypatch.setattr("models.serving_v2.CandidateMlflowModelLoaderV2", Loader)
    assert predict_candidate_v2(frame, "2023-01-30") == 123.0
