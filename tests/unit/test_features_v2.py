import numpy as np
import pandas as pd
import pytest

from features.contracts import FEATURE_CONTRACT_V1, FEATURE_CONTRACT_V2
from features.pipeline import (
    FeaturePreparationError,
    build_online_features_v2,
    create_features_v2,
)
from ingestion.constants import EXPECTED_COLUMNS, TARGET_COLUMN


def source_frame(dates: pd.DatetimeIndex, values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Fecha": dates,
            TARGET_COLUMN: values,
            "Generación kWh": values,
            "Demanda No Atendida kWh": [None] * len(dates),
            "Exportaciones kWh": [None] * len(dates),
            "Importaciones kWh": [None] * len(dates),
        },
        columns=EXPECTED_COLUMNS,
    )


def test_v2_contract_adds_five_ordered_predictors_without_changing_v1() -> None:
    assert len(FEATURE_CONTRACT_V1.predictor_columns) == 22
    assert len(FEATURE_CONTRACT_V2.predictor_columns) == 27
    assert FEATURE_CONTRACT_V2.predictor_columns[-5:] == (
        "demand_at_reference_date",
        "lag_2",
        "lag_3",
        "rolling_mean_3_including_reference",
        "rolling_std_3_including_reference",
    )


def test_v2_short_memory_uses_reference_date_and_calendar_days() -> None:
    dates = pd.date_range("2023-01-01", periods=40, freq="D")
    result = create_features_v2(source_frame(dates, list(range(40))))
    row = result.loc[result["reference_date"] == pd.Timestamp("2023-01-29")].iloc[0]

    assert row["demand_at_reference_date"] == 28
    assert row["lag_2"] == 26
    assert row["lag_3"] == 25
    assert row["rolling_mean_3_including_reference"] == pytest.approx(27)
    assert row["rolling_std_3_including_reference"] == pytest.approx(np.std([26, 27, 28], ddof=1))


def test_v2_never_crosses_known_calendar_gap() -> None:
    dates = pd.date_range("2015-11-20", "2016-02-10", freq="D")
    dates = dates[dates != pd.Timestamp("2015-12-31")]
    frame = source_frame(dates, list(range(len(dates))))
    result = create_features_v2(frame)

    assert not result["reference_date"].between("2015-12-31", "2016-01-28").any()
    with pytest.raises(FeaturePreparationError, match="Insufficient or incomplete"):
        build_online_features_v2(frame, "2016-01-02")


def test_v2_batch_and_online_rows_are_identical_and_future_safe() -> None:
    dates = pd.date_range("2023-01-01", periods=50, freq="D")
    frame = source_frame(dates, list(range(50)))
    batch = create_features_v2(frame)
    reference_date = pd.Timestamp("2023-02-10")
    batch_row = batch.loc[batch["reference_date"] == reference_date].iloc[0]
    online = build_online_features_v2(frame, reference_date + pd.Timedelta(days=1)).iloc[0]

    assert online.loc[list(FEATURE_CONTRACT_V2.predictor_columns)].to_dict() == pytest.approx(
        batch_row.loc[list(FEATURE_CONTRACT_V2.predictor_columns)].to_dict()
    )

    changed = frame.copy()
    changed.loc[changed["Fecha"] == reference_date + pd.Timedelta(days=1), TARGET_COLUMN] = 999999.0
    changed_row = create_features_v2(changed).loc[
        lambda values: values["reference_date"] == reference_date
    ].iloc[0]
    assert changed_row.loc[list(FEATURE_CONTRACT_V2.predictor_columns)].to_dict() == pytest.approx(
        batch_row.loc[list(FEATURE_CONTRACT_V2.predictor_columns)].to_dict()
    )
