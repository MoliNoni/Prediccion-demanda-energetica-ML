"""Compare one justified additional model with existing candidates before Test."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
from run_phase11_feature_experiments import (
    HISTORICAL_DEMAND_PATH,
    experimental_features,
)
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor

from evaluation.metrics import mae, rmse, smape, wape
from models.training import (
    DATE_COLUMN,
    INPUT_DATASET,
    PREDICTOR_COLUMNS,
    TARGET_COLUMN,
    build_selected_model,
)

OUTPUT_PATH = Path("data/processed/phase11_model_comparison.json")
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


def build_models() -> dict[str, object]:
    return {
        "HistGradientBoostingRegressor": build_selected_model(),
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=200,
            random_state=42,
            n_jobs=-1,
        ),
        "ExtraTreesRegressor": ExtraTreesRegressor(
            n_estimators=200,
            random_state=42,
            n_jobs=-1,
        ),
    }


def run(
    input_path: Path = INPUT_DATASET,
    historical_demand_path: Path = HISTORICAL_DEMAND_PATH,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    base = pd.read_parquet(input_path).sort_values(DATE_COLUMN).reset_index(drop=True)
    frame = experimental_features(base, pd.read_parquet(historical_demand_path))
    usable = frame.dropna(subset=list(SHORT_MEMORY_COLUMNS))
    usable_dates = pd.to_datetime(usable[DATE_COLUMN], errors="raise")
    train = usable.loc[usable_dates.dt.year.between(2000, 2019)]
    validation = usable.loc[usable_dates.dt.year.between(2020, 2021)]
    columns = (*PREDICTOR_COLUMNS, *SHORT_MEMORY_COLUMNS)
    results = []
    for name, model in build_models().items():
        model.fit(train.loc[:, columns], train[TARGET_COLUMN])
        prediction = model.predict(validation.loc[:, columns])
        results.append(
            {
                "model": name,
                "metrics": metric_values(validation[TARGET_COLUMN], pd.Series(prediction)),
            }
        )
    output = {
        "purpose": "Pre-test model comparison using the stable short-memory features",
        "hypothesis": (
            "ExtraTrees may reduce remaining nonlinear seasonal error through more diverse "
            "tree splits than the current tree ensembles."
        ),
        "train_years": "2000-2019",
        "validation_years": "2020-2021",
        "test_years_used": [],
        "features_added": list(SHORT_MEMORY_COLUMNS),
        "train_records": len(train),
        "validation_records": len(validation),
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    run()
    print(f"Output: {OUTPUT_PATH}")
