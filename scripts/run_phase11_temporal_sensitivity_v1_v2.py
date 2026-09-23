"""Run the isolated Phase 11 post-pandemic temporal-sensitivity analysis."""

import json
from pathlib import Path

import pandas as pd

from evaluation.temporal_sensitivity import compare_alternative_temporal_split
from models.training import INPUT_DATASET
from models.training_v2 import INPUT_DATASET_V2

OUTPUT_PATH = Path("data/processed/temporal_validation_sensitivity_v1_v2.json")


def run(
    v1_input_path: Path = INPUT_DATASET,
    v2_input_path: Path = INPUT_DATASET_V2,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, object]:
    if not v1_input_path.is_file() or not v2_input_path.is_file():
        raise FileNotFoundError("V1 and v2 feature datasets are required")
    result = compare_alternative_temporal_split(
        pd.read_parquet(v1_input_path), pd.read_parquet(v2_input_path)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    output = run()
    print(f"Output: {OUTPUT_PATH}")
    print(f"Validation/Test comparisons: {len(output['results'])}")
