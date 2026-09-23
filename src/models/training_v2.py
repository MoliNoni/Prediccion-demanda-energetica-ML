import json
from pathlib import Path
from typing import Any

import pandas as pd

from features.contracts import FEATURE_CONTRACT_V2
from models.training import DATE_COLUMN, TARGET_COLUMN, build_selected_model, split_temporally

INPUT_DATASET_V2 = Path("data/processed/energy_demand_features_h1_v2.parquet")
PREDICTIONS_OUTPUT_V2 = Path("data/processed/model_predictions_h1_v2.parquet")
METADATA_OUTPUT_V2 = Path("data/processed/modeling_run_metadata_v2.json")
PREDICTOR_COLUMNS_V2 = FEATURE_CONTRACT_V2.predictor_columns


def train_v2_model(frame: pd.DataFrame) -> tuple[object, dict[str, Any]]:
    required = (*PREDICTOR_COLUMNS_V2, TARGET_COLUMN, DATE_COLUMN)
    missing = [column for column in required if column not in frame]
    if missing:
        raise ValueError(f"Missing v2 modeling columns: {missing}")
    split = split_temporally(frame.sort_values(DATE_COLUMN).reset_index(drop=True))
    model = build_selected_model()
    model.fit(split.train.loc[:, PREDICTOR_COLUMNS_V2], split.train[TARGET_COLUMN])
    return model, {
        "feature_set_version": FEATURE_CONTRACT_V2.version,
        "predictor_columns": list(PREDICTOR_COLUMNS_V2),
        "train_years": "2000-2019",
        "train_records": len(split.train),
        "model": model.get_params(),
    }


def train_and_predict_v2(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    model, metadata = train_v2_model(frame)
    split = split_temporally(frame.sort_values(DATE_COLUMN).reset_index(drop=True))
    predictions = []
    for split_name, partition in (("validation", split.validation), ("test", split.test)):
        values = partition.loc[:, ["reference_date", DATE_COLUMN, TARGET_COLUMN]].copy()
        values["split"] = split_name
        values["HistGradientBoostingRegressor_v2_prediction"] = model.predict(
            partition.loc[:, PREDICTOR_COLUMNS_V2]
        )
        predictions.append(values)
    metadata.update(
        {
            "input_dataset": str(INPUT_DATASET_V2),
            "target": TARGET_COLUMN,
            "horizon": "H+1",
            "validation_years": "2020-2021",
            "test_years": "2022-2023",
            "validation_records": len(split.validation),
            "test_records": len(split.test),
        }
    )
    return pd.concat(predictions, ignore_index=True), metadata


def run_modeling_v2(
    input_path: Path = INPUT_DATASET_V2,
    predictions_path: Path = PREDICTIONS_OUTPUT_V2,
    metadata_path: Path = METADATA_OUTPUT_V2,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not input_path.is_file():
        raise FileNotFoundError(f"V2 modeling input not found: {input_path}")
    predictions, metadata = train_and_predict_v2(pd.read_parquet(input_path))
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(predictions_path, index=False)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return predictions, metadata
