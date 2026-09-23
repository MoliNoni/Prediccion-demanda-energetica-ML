import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor

from features.pipeline import FEATURE_COLUMNS

INPUT_DATASET = Path("data/processed/energy_demand_features_h1.parquet")
PREDICTIONS_OUTPUT = Path("data/processed/model_predictions_h1.parquet")
METADATA_OUTPUT = Path("data/processed/modeling_run_metadata.json")
TARGET_COLUMN = "target_h1"
DATE_COLUMN = "target_date"
PREDICTOR_COLUMNS = tuple(
    column
    for column in FEATURE_COLUMNS
    if column not in {"reference_date", "target_date", TARGET_COLUMN}
)


@dataclass(frozen=True)
class TemporalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def split_temporally(frame: pd.DataFrame) -> TemporalSplit:
    dates = pd.to_datetime(frame[DATE_COLUMN], errors="raise")
    train_mask = dates.dt.year.between(2000, 2019)
    validation_mask = dates.dt.year.between(2020, 2021)
    test_mask = dates.dt.year.between(2022, 2023)
    split = TemporalSplit(
        train=frame.loc[train_mask].copy(),
        validation=frame.loc[validation_mask].copy(),
        test=frame.loc[test_mask].copy(),
    )
    if not split.train[DATE_COLUMN].lt(split.validation[DATE_COLUMN].min()).all():
        raise ValueError("Train and validation periods overlap or are unordered")
    if not split.validation[DATE_COLUMN].lt(split.test[DATE_COLUMN].min()).all():
        raise ValueError("Validation and test periods overlap or are unordered")
    if any(part.empty for part in (split.train, split.validation, split.test)):
        raise ValueError("Every temporal split must contain records")
    return split


def build_baseline(frame: pd.DataFrame) -> pd.Series:
    """Use lag_7: y(t-7) equals y(t-6) relative to target t+1."""
    return frame["lag_7"].rename("baseline_prediction")


def _build_models() -> dict[str, object]:
    return {
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=200,
            random_state=42,
            n_jobs=-1,
        ),
        "HistGradientBoostingRegressor": HistGradientBoostingRegressor(
            max_iter=200,
            learning_rate=0.05,
            max_leaf_nodes=31,
            random_state=42,
        ),
    }


def build_selected_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=200,
        learning_rate=0.05,
        max_leaf_nodes=31,
        random_state=42,
    )


def train_selected_model(
    frame: pd.DataFrame,
) -> tuple[HistGradientBoostingRegressor, dict[str, object]]:
    required_columns = (*PREDICTOR_COLUMNS, TARGET_COLUMN, DATE_COLUMN)
    missing = [column for column in required_columns if column not in frame]
    if missing:
        raise ValueError(f"Missing modeling columns: {missing}")
    split = split_temporally(frame.sort_values(DATE_COLUMN).reset_index(drop=True))
    model = build_selected_model()
    model.fit(split.train.loc[:, PREDICTOR_COLUMNS], split.train[TARGET_COLUMN])
    return model, {
        "input_dataset": str(INPUT_DATASET),
        "target": TARGET_COLUMN,
        "horizon": "H+1",
        "predictor_columns": list(PREDICTOR_COLUMNS),
        "train_years": "2000-2019",
        "train_records": len(split.train),
        "model": model.get_params(),
    }


def train_and_predict(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    required_columns = (*PREDICTOR_COLUMNS, TARGET_COLUMN, DATE_COLUMN)
    missing = [column for column in required_columns if column not in frame]
    if missing:
        raise ValueError(f"Missing modeling columns: {missing}")
    split = split_temporally(frame.sort_values(DATE_COLUMN).reset_index(drop=True))
    x_train = split.train.loc[:, PREDICTOR_COLUMNS]
    y_train = split.train[TARGET_COLUMN]
    predictions = []
    models = _build_models()
    for split_name, partition in (("validation", split.validation), ("test", split.test)):
        values = partition.loc[:, ["reference_date", DATE_COLUMN, TARGET_COLUMN]].copy()
        values["split"] = split_name
        values["baseline_prediction"] = build_baseline(partition).to_numpy()
        x_partition = partition.loc[:, PREDICTOR_COLUMNS]
        for model_name, model in models.items():
            model.fit(x_train, y_train)
            values[f"{model_name}_prediction"] = model.predict(x_partition)
        predictions.append(values)

    result = pd.concat(predictions, ignore_index=True)
    metadata = {
        "input_dataset": str(INPUT_DATASET),
        "target": TARGET_COLUMN,
        "horizon": "H+1",
        "predictor_columns": list(PREDICTOR_COLUMNS),
        "train_years": "2000-2019",
        "validation_years": "2020-2021",
        "test_years": "2022-2023",
        "train_records": len(split.train),
        "validation_records": len(split.validation),
        "test_records": len(split.test),
        "models": {
            name: model.get_params() for name, model in models.items()
        },
        "metrics": "not calculated in this phase",
        "mlflow": "not configured in this phase",
    }
    return result, metadata


def run_modeling(
    input_path: Path = INPUT_DATASET,
    predictions_path: Path = PREDICTIONS_OUTPUT,
    metadata_path: Path = METADATA_OUTPUT,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if not input_path.is_file():
        raise FileNotFoundError(f"Modeling input not found: {input_path}")
    frame = pd.read_parquet(input_path)
    predictions, metadata = train_and_predict(frame)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(predictions_path, index=False)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return predictions, metadata
