from collections.abc import Iterable
from pathlib import Path


class IngestionNotConfiguredError(RuntimeError):
    """Raised until a verified source and schema are selected."""


def ingest_from_source(source_uri: str, destination: Path) -> None:
    """Reserve the ingestion boundary without assuming XM's current format."""
    if not source_uri.strip():
        raise ValueError("source_uri must not be empty")
    if destination == Path():
        raise ValueError("destination must be a valid path")
    raise IngestionNotConfiguredError(
        "The source format must be approved in 02_DATA_SPECIFICATION.md before ingestion."
    )


def validate_source_records(records: Iterable[object]) -> None:
    """Keep source validation separate from transport and persistence."""
    if records is None:
        raise ValueError("records must not be None")
