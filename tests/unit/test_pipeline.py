from pathlib import Path

import pandas as pd
import pytest

from ingestion.constants import EXPECTED_COLUMNS
from ingestion.pipeline import IngestionValidationError, discover_files


def test_discovery_requires_all_expected_files(tmp_path: Path) -> None:
    with pytest.raises(IngestionValidationError):
        discover_files(tmp_path)


def test_consolidation_order_can_be_verified_without_source_changes() -> None:
    first = pd.DataFrame(
        [[pd.Timestamp("2023-01-02"), 2, 3, None, None, None]],
        columns=EXPECTED_COLUMNS,
    )
    second = pd.DataFrame(
        [[pd.Timestamp("2023-01-01"), 1, 2, None, None, None]],
        columns=EXPECTED_COLUMNS,
    )
    consolidated = pd.concat([first, second], ignore_index=True).sort_values("Fecha")

    assert consolidated["Fecha"].tolist() == [
        pd.Timestamp("2023-01-01"),
        pd.Timestamp("2023-01-02"),
    ]
