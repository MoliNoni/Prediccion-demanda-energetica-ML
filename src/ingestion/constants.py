from pathlib import Path

EXPECTED_SHEET = "Demanda_Energia_SIN"
ALTERNATIVE_SHEET = "Demanda_Energia_SIN.rdl"
EXPECTED_COLUMNS = (
    "Fecha",
    "Demanda Energia SIN kWh",
    "Generación kWh",
    "Demanda No Atendida kWh",
    "Exportaciones kWh",
    "Importaciones kWh",
)
TARGET_COLUMN = "Demanda Energia SIN kWh"
AUXILIARY_COLUMNS = EXPECTED_COLUMNS[2:]
RAW_DIRECTORY = Path("data/raw")
INTERIM_OUTPUT = Path("data/interim/energy_demand_daily.parquet")
AUDIT_OUTPUT = Path("data/interim/ingestion_audit.json")
