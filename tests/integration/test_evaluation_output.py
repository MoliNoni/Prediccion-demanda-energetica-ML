import json
from pathlib import Path

import pandas as pd

from evaluation.run_evaluation import run_evaluation


def test_evaluation_writes_json(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "target_date": pd.to_datetime(["2020-01-01", "2022-01-01"]),
            "target_h1": [10.0, 10.0],
            "split": ["validation", "test"],
            "baseline_prediction": [9.0, 9.0],
            "RandomForestRegressor_prediction": [8.0, 8.0],
            "HistGradientBoostingRegressor_prediction": [7.0, 7.0],
        }
    )
    source = tmp_path / "predictions.parquet"
    output = tmp_path / "evaluation_results_h1.json"
    frame.to_parquet(source, index=False)

    result = run_evaluation(source, output)

    assert (
        json.loads(output.read_text(encoding="utf-8"))["selected_model_by_validation"] == "baseline"
    )
    assert result["test_used_for_selection"] is False
