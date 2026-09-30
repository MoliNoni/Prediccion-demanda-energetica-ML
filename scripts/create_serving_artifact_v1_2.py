"""Create the v1.2.0 serving artifact.

Run it inside the backend container so the MLflow artifact_uri is ``file:///app/mlruns/...``,
the same convention as v1.1.0::

    docker compose run --rm --no-deps -v ./src:/app/src -v ./scripts:/app/scripts \\
        backend python scripts/create_serving_artifact_v1_2.py
"""

import argparse
from pathlib import Path

from models.serving_ratio import SERVING_METADATA_PATH_RATIO, create_serving_artifact_v1_2
from models.serving_v2 import DEFAULT_TRACKING_DIRECTORY

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refit and log the v1.2.0 serving artifact")
    parser.add_argument("--tracking-directory", type=Path, default=DEFAULT_TRACKING_DIRECTORY)
    parser.add_argument("--metadata-path", type=Path, default=SERVING_METADATA_PATH_RATIO)
    arguments = parser.parse_args()
    metadata = create_serving_artifact_v1_2(
        metadata_path=arguments.metadata_path, tracking_directory=arguments.tracking_directory
    )
    print(f"MLflow run: {metadata['run_id']}")
    print(f"Model URI: {metadata['model_uri']}")
    print(f"Tracking URI: {metadata['tracking_uri']}")
    print(f"Metadata: {arguments.metadata_path}")
