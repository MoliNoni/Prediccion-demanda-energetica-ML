"""Perform the single locked Test evaluation for the Phase 11 selected candidate."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
from run_phase11_feature_experiments import (
    HISTORICAL_DEMAND_PATH,
    experimental_features,
)

from evaluation.metrics import mae, rmse, smape, wape
from models.training import (
    DATE_COLUMN,
    INPUT_DATASET,
    PREDICTOR_COLUMNS,
    TARGET_COLUMN,
    build_selected_model,
)

OUTPUT_PATH = Path("data/processed/phase11_final_test_evaluation.json")
SHORT_MEMORY_COLUMNS = (
    "demand_at_reference_date",
    "lag_2",
    "lag_3",
    "rolling_mean_3_including_reference",
    "rolling_std_3_including_reference",
)


def metric_values(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    return {
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "smape": smape(actual, predicted),
        "wape": wape(actual, predicted),
    }


def evaluate(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    columns: tuple[str, ...],
) -> dict[str, float]:
    model = build_selected_model()
    model.fit(train.loc[:, columns], train[TARGET_COLUMN])
    prediction = model.predict(evaluation.loc[:, columns])
    return metric_values(evaluation[TARGET_COLUMN], pd.Series(prediction))


def run(
    input_path: Path = INPUT_DATASET,
    historical_demand_path: Path = HISTORICAL_DEMAND_PATH,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    base = pd.read_parquet(input_path).sort_values(DATE_COLUMN).reset_index(drop=True)
    dates = pd.to_datetime(base[DATE_COLUMN], errors="raise")
    base_train = base.loc[dates.dt.year.between(2000, 2019)]
    base_test = base.loc[dates.dt.year.between(2022, 2023)]

    augmented = experimental_features(base, pd.read_parquet(historical_demand_path))
    usable = augmented.dropna(subset=list(SHORT_MEMORY_COLUMNS))
    usable_dates = pd.to_datetime(usable[DATE_COLUMN], errors="raise")
    candidate_train = usable.loc[usable_dates.dt.year.between(2000, 2019)]
    candidate_test = usable.loc[usable_dates.dt.year.between(2022, 2023)]

    output = {
        "purpose": "Single final Test comparison after pre-Test candidate selection",
        "selection_source": "Validation 2020-2021 and expanding windows 2016-2021 only",
        "test_reuse_rule": (
            "No further feature, model, or hyperparameter selection follows this result."
        ),
        "train_years": "2000-2019",
        "test_years": "2022-2023",
        "approved_hgb_features": {
            "records": len(base_test),
            "metrics": evaluate(base_train, base_test, PREDICTOR_COLUMNS),
        },
        "selected_short_memory_features": {
            "added_features": list(SHORT_MEMORY_COLUMNS),
            "records": len(candidate_test),
            "metrics": evaluate(
                candidate_train,
                candidate_test,
                (*PREDICTOR_COLUMNS, *SHORT_MEMORY_COLUMNS),
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    run()
    print(f"Output: {OUTPUT_PATH}")
