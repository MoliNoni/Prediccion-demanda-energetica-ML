import pandas as pd

from ingestion.constants import EXPECTED_COLUMNS
from validation.audit import audit_frame, normalize_frame


def make_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["2023-01-01", "10", "11", None, None, None],
            ["2023-01-02", "12", "13", "1", "2", None],
        ],
        columns=EXPECTED_COLUMNS,
    )


def test_normalize_preserves_schema_and_nulls() -> None:
    normalized = normalize_frame(make_frame())

    assert list(normalized.columns) == list(EXPECTED_COLUMNS)
    assert pd.isna(normalized.loc[0, "Importaciones kWh"])
    assert normalized["Fecha"].dt.normalize().tolist() == list(normalized["Fecha"])
    assert normalized["Demanda Energia SIN kWh"].tolist() == [10, 12]


def test_invalid_target_is_blocking() -> None:
    frame = make_frame()
    frame.loc[0, "Demanda Energia SIN kWh"] = "invalid"

    audit = audit_frame(frame, file_name="Demanda_Energia_SIN_2023.xlsx", year=2023)

    assert audit.status == "BLOCKED"
    assert any("target" in error for error in audit.blockers)


def test_invalid_date_is_blocking() -> None:
    frame = make_frame()
    frame.loc[0, "Fecha"] = "not-a-date"

    audit = audit_frame(frame, file_name="Demanda_Energia_SIN_2023.xlsx", year=2023)

    assert audit.status == "BLOCKED"
    assert any("Fecha" in error for error in audit.blockers)


def test_wrong_year_is_blocking() -> None:
    frame = make_frame()
    frame.loc[0, "Fecha"] = "2022-12-31"

    audit = audit_frame(frame, file_name="Demanda_Energia_SIN_2023.xlsx", year=2023)

    assert audit.status == "BLOCKED"
    assert any("año" in error for error in audit.blockers)


def test_duplicate_date_is_blocking() -> None:
    frame = make_frame()
    frame.loc[1, "Fecha"] = "2023-01-01"

    audit = audit_frame(frame, file_name="Demanda_Energia_SIN_2023.xlsx", year=2023)

    assert audit.status == "BLOCKED"
    assert audit.duplicate_dates == 1


def test_missing_date_is_observation() -> None:
    frame = make_frame()
    frame.loc[1, "Fecha"] = "2023-01-03"

    audit = audit_frame(frame, file_name="Demanda_Energia_SIN_2023.xlsx", year=2023)

    assert audit.status == "OBSERVATIONS"
    assert audit.missing_dates == ["2023-01-02"]
    assert not audit.blockers


def test_known_2015_absence_is_observation() -> None:
    frame = pd.DataFrame(
        [["2015-12-30", "10", "11", None, None, None]],
        columns=EXPECTED_COLUMNS,
    )

    audit = audit_frame(frame, file_name="Demanda_Energia_SIN_2015.xlsx", year=2015)

    assert audit.status == "OBSERVATIONS"
    assert any("2015-12-31" in observation for observation in audit.observations)
