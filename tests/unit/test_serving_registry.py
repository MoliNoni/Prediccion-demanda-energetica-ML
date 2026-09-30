import pytest

from models.serving import MODEL_HORIZON, MODEL_NAME, MODEL_VERSION, ServingArtifactUnavailableError
from models.serving_ratio import (
    MODEL_HORIZON_RATIO,
    MODEL_NAME_RATIO,
    MODEL_VERSION_RATIO,
    build_online_features_ratio,
)
from models.serving_registry import ServingModelRegistry
from models.serving_v2 import MODEL_HORIZON_V2, MODEL_NAME_V2, MODEL_VERSION_V2


class Loader:
    def __init__(self, metadata: dict[str, object]) -> None:
        self.metadata = metadata
        self.model = object()

    def load(self):
        return self.model, self.metadata


def metadata(name: str, version: str, horizon: int) -> dict[str, object]:
    return {
        "model_name": name,
        "model_version": version,
        "horizon": horizon,
        "predictor_columns": ["lag_1"],
    }


@pytest.mark.parametrize(
    ("name", "version", "horizon"),
    [
        (MODEL_NAME, MODEL_VERSION, MODEL_HORIZON),
        (MODEL_NAME_V2, MODEL_VERSION_V2, MODEL_HORIZON_V2),
        (MODEL_NAME_RATIO, MODEL_VERSION_RATIO, MODEL_HORIZON_RATIO),
    ],
)
def test_registry_selects_the_loader_matching_the_active_model(name, version, horizon) -> None:
    v1 = Loader(metadata(MODEL_NAME, MODEL_VERSION, MODEL_HORIZON))
    v2 = Loader(metadata(MODEL_NAME_V2, MODEL_VERSION_V2, MODEL_HORIZON_V2))
    ratio = Loader(metadata(MODEL_NAME_RATIO, MODEL_VERSION_RATIO, MODEL_HORIZON_RATIO))

    _, loaded_metadata, feature_builder = ServingModelRegistry(
        v1_loader=v1, v2_loader=v2, ratio_loader=ratio
    ).load({"name": name, "version": version, "horizon": horizon})

    assert loaded_metadata["model_version"] == version
    assert callable(feature_builder)


def test_registry_rejects_an_unknown_active_model() -> None:
    registry = ServingModelRegistry(
        v1_loader=Loader(metadata(MODEL_NAME, MODEL_VERSION, MODEL_HORIZON)),
        v2_loader=Loader(metadata(MODEL_NAME_V2, MODEL_VERSION_V2, MODEL_HORIZON_V2)),
    )

    with pytest.raises(ServingArtifactUnavailableError, match="no approved serving route"):
        registry.load({"name": MODEL_NAME, "version": "9.9.9", "horizon": 1})


def test_registry_rejects_artifact_metadata_that_differs_from_database_selection() -> None:
    registry = ServingModelRegistry(
        v1_loader=Loader(metadata(MODEL_NAME, MODEL_VERSION, MODEL_HORIZON)),
        v2_loader=Loader(metadata(MODEL_NAME_V2, MODEL_VERSION, MODEL_HORIZON_V2)),
    )

    with pytest.raises(ServingArtifactUnavailableError, match="does not match"):
        registry.load(
            {"name": MODEL_NAME_V2, "version": MODEL_VERSION_V2, "horizon": MODEL_HORIZON_V2}
        )


def test_registry_resolves_v1_2_0_to_the_ratio_loader_and_builder() -> None:
    loader = Loader(metadata(MODEL_NAME_RATIO, "1.2.0", 1))

    model, loaded, feature_builder = ServingModelRegistry(ratio_loader=loader).load(
        {"name": MODEL_NAME_V2, "version": "1.2.0", "horizon": 1}
    )

    assert model is loader.model
    assert loaded is loader.metadata
    assert feature_builder is build_online_features_ratio
