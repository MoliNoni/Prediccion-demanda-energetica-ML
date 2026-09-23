import pytest

from features.service import FeaturePipelineNotConfiguredError, build_features
from models.service import ModelNotConfiguredError, train_model


def test_feature_pipeline_is_blocked_before_data_specification() -> None:
    with pytest.raises(FeaturePipelineNotConfiguredError):
        build_features(object())


def test_model_training_is_blocked_before_data_specification() -> None:
    with pytest.raises(ModelNotConfiguredError):
        train_model(object())
