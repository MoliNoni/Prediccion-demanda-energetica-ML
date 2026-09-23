class ValidationNotConfiguredError(RuntimeError):
    """Raised until the real dataset contract is approved."""


def validate_dataset(dataset: object) -> None:
    """Reserve dataset validation without inventing columns or units."""
    if dataset is None:
        raise ValueError("dataset must not be None")
    raise ValidationNotConfiguredError(
        "Dataset validation rules must be defined in 02_DATA_SPECIFICATION.md."
    )
