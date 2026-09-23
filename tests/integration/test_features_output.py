from pathlib import Path

import pandas as pd

from features.pipeline import FEATURE_COLUMNS, build_feature_dataset
from ingestion.constants import EXPECTED_COLUMNS


def test_feature_dataset_output_is_parquet(tmp_path: Path) -> None:
    dates = pd.date_range("2023-01-01", periods=40, freq="D")
    frame = pd.DataFrame(
        {
            "Fecha": dates,
            "Demanda Energia SIN kWh": range(40),
            "Generación kWh": range(40),
            "Demanda No Atendida kWh": [None] * 40,
            "Exportaciones kWh": [None] * 40,
            "Importaciones kWh": [None] * 40,
        },
        columns=EXPECTED_COLUMNS,
    )
    source = tmp_path / "energy_demand_daily.parquet"
    output = tmp_path / "energy_demand_features_h1.parquet"
    frame.to_parquet(source, index=False)

    result = build_feature_dataset(source, output)

    assert output.exists()
    assert len(result) == len(pd.read_parquet(output))
    assert result.columns.tolist() == list(FEATURE_COLUMNS)
