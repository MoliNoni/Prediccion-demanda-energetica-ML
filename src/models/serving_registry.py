"""Internal versioned serving route; public HTTP routes do not select versions."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from features.pipeline import build_online_features, build_online_features_v2
from models.serving import (
    MODEL_HORIZON,
    MODEL_NAME,
    MODEL_VERSION,
    MlflowModelLoader,
    ServingArtifactUnavailableError,
)
from models.serving_ratio import (
    MODEL_HORIZON_RATIO,
    MODEL_NAME_RATIO,
    MODEL_VERSION_RATIO,
    RatioMlflowModelLoader,
    build_online_features_ratio,
)
from models.serving_v2 import (
    MODEL_HORIZON_V2,
    MODEL_NAME_V2,
    MODEL_VERSION_V2,
    CandidateMlflowModelLoaderV2,
    CandidateServingArtifactUnavailableError,
)

ModelIdentity = tuple[str, str, int]
FeatureBuilder = Callable[[pd.DataFrame, date], pd.DataFrame]

# version -> (name, horizon, loader type) for every model with an approved serving route.
SUPPORTED_SERVING_MODELS: dict[str, tuple[str, int, type]] = {
    MODEL_VERSION: (MODEL_NAME, MODEL_HORIZON, MlflowModelLoader),
    MODEL_VERSION_V2: (MODEL_NAME_V2, MODEL_HORIZON_V2, CandidateMlflowModelLoaderV2),
    MODEL_VERSION_RATIO: (MODEL_NAME_RATIO, MODEL_HORIZON_RATIO, RatioMlflowModelLoader),
}


class ServingModelRegistry:
    """Resolve the database-selected model to its artifact and feature contract."""

    def __init__(
        self,
        *,
        v1_loader: MlflowModelLoader | None = None,
        v2_loader: CandidateMlflowModelLoaderV2 | None = None,
        ratio_loader: RatioMlflowModelLoader | None = None,
    ) -> None:
        self._routes: dict[ModelIdentity, tuple[Any, FeatureBuilder]] = {
            (MODEL_NAME, MODEL_VERSION, MODEL_HORIZON): (
                v1_loader or MlflowModelLoader(),
                build_online_features,
            ),
            (MODEL_NAME_V2, MODEL_VERSION_V2, MODEL_HORIZON_V2): (
                v2_loader or CandidateMlflowModelLoaderV2(),
                build_online_features_v2,
            ),
            (MODEL_NAME_RATIO, MODEL_VERSION_RATIO, MODEL_HORIZON_RATIO): (
                ratio_loader or RatioMlflowModelLoader(),
                build_online_features_ratio,
            ),
        }

    def load(self, active_model: dict[str, object]) -> tuple[Any, dict[str, Any], FeatureBuilder]:
        identity = (
            str(active_model["name"]),
            str(active_model["version"]),
            int(active_model["horizon"]),
        )
        route = self._routes.get(identity)
        if route is None:
            raise ServingArtifactUnavailableError("Active model has no approved serving route")
        loader, feature_builder = route
        try:
            model, metadata = loader.load()
        except CandidateServingArtifactUnavailableError as error:
            raise ServingArtifactUnavailableError("Active v2 artifact is unavailable") from error
        if (
            metadata.get("model_name") != identity[0]
            or metadata.get("model_version") != identity[1]
            or metadata.get("horizon") != identity[2]
        ):
            raise ServingArtifactUnavailableError("Active model does not match serving artifact")
        return model, metadata, feature_builder
