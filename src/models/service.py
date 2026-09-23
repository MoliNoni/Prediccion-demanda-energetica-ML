class ModelNotConfiguredError(RuntimeError):
    """Raised because no model may be trained before data specification approval."""


def train_model(features: object) -> object:
    """Explicitly prevent definitive training during project foundation."""
    if features is None:
        raise ValueError("features must not be None")
    raise ModelNotConfiguredError(
        "Definitive model training is blocked until 02_DATA_SPECIFICATION.md is approved."
    )
