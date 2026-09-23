"""Explicit, reversible production promotion command. It is never run by tests."""

import argparse
from uuid import UUID

from database.repositories import ModelRepository
from database.session import create_database_engine
from models.serving import MODEL_HORIZON, MODEL_NAME, MODEL_VERSION, MlflowModelLoader
from models.serving_v2 import (
    MODEL_HORIZON_V2,
    MODEL_NAME_V2,
    MODEL_VERSION_V2,
    CandidateMlflowModelLoaderV2,
)

SUPPORTED_MODELS = {
    MODEL_VERSION: (MODEL_NAME, MODEL_HORIZON, MlflowModelLoader),
    MODEL_VERSION_V2: (MODEL_NAME_V2, MODEL_HORIZON_V2, CandidateMlflowModelLoaderV2),
}


def promote_serving_model(version: str, *, execute: bool = False) -> str:
    """Validate a registered artifact and optionally make it the sole active model."""
    try:
        name, horizon, loader_type = SUPPORTED_MODELS[version]
    except KeyError as error:
        raise ValueError(f"Unsupported serving model version: {version}") from error
    loader_type().load()
    engine = create_database_engine()
    with engine.connect() as connection:
        model = ModelRepository().get_by_identity(connection, name=name, version=version)
        if model is None or model["horizon"] != horizon:
            raise ValueError("Registered model is missing or has an incompatible horizon")
        model_id = str(model["id"])
    if not execute:
        return model_id
    with engine.begin() as connection:
        ModelRepository().promote(connection, UUID(model_id))
    return model_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate or promote a serving model")
    parser.add_argument("version", choices=sorted(SUPPORTED_MODELS))
    parser.add_argument(
        "--execute", action="store_true", help="Apply the promotion after validation"
    )
    arguments = parser.parse_args()
    action = "Promoted" if arguments.execute else "Validated (dry run)"
    model_id = promote_serving_model(arguments.version, execute=arguments.execute)
    print(f"{action} serving model id: {model_id}")
