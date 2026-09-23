class FeaturePipelineNotConfiguredError(RuntimeError):
    """Raised until the target frequency and horizon are known."""


def build_features(dataset: object) -> object:
    """Reserve feature engineering without training or selecting a target."""
    if dataset is None:
        raise ValueError("dataset must not be None")
    raise FeaturePipelineNotConfiguredError(
        "Feature rules must be defined after the data specification is approved."
    )
