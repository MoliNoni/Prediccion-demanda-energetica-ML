"""Register a serving model row.

Without arguments it keeps the historical behavior (register and activate v1.0.0). With
``--inactive`` it inserts the row of another supported version as INACTIVE, so it can be used
for backfills before a separate ``promote_serving_model.py`` activates it. ``--inactive`` is a
dry run unless ``--execute`` is given; it never changes which model is active.
"""

import argparse

from database.repositories import ModelRepository
from database.session import create_database_engine
from models.serving import MODEL_HORIZON, MODEL_NAME, MODEL_VERSION, MlflowModelLoader
from models.serving_registry import SUPPORTED_SERVING_MODELS


def register_serving_model() -> str:
    MlflowModelLoader().load()
    engine = create_database_engine()
    with engine.begin() as connection:
        repository = ModelRepository()
        existing = repository.get_by_identity(
            connection,
            name=MODEL_NAME,
            version=MODEL_VERSION,
        )
        if existing is None:
            model_id = repository.create(
                connection,
                name=MODEL_NAME,
                version=MODEL_VERSION,
                horizon=MODEL_HORIZON,
                is_active=True,
            )
        else:
            if existing["horizon"] != MODEL_HORIZON:
                raise ValueError("Existing serving model has an incompatible horizon")
            repository.promote(connection, existing["id"])
            model_id = existing["id"]
    return str(model_id)


def register_inactive_model(version: str, *, execute: bool = False) -> tuple[str | None, bool]:
    """Validate the artifact and insert the model inactive; return (id, created).

    Idempotent: an existing row is left untouched. Without ``execute`` nothing is written and
    the id is None when the row does not exist yet.
    """
    try:
        name, horizon, loader_type = SUPPORTED_SERVING_MODELS[version]
    except KeyError as error:
        raise ValueError(f"Unsupported serving model version: {version}") from error
    loader_type().load()
    engine = create_database_engine()
    try:
        with engine.begin() as connection:
            repository = ModelRepository()
            existing = repository.get_by_identity(connection, name=name, version=version)
            if existing is not None:
                if existing["horizon"] != horizon:
                    raise ValueError("Existing serving model has an incompatible horizon")
                return str(existing["id"]), False
            if not execute:
                return None, False
            model_id = repository.create(
                connection, name=name, version=version, horizon=horizon, is_active=False
            )
            return str(model_id), True
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register a serving model")
    parser.add_argument("--inactive", action="store_true", help="register a version as inactive")
    parser.add_argument("--version", choices=sorted(SUPPORTED_SERVING_MODELS))
    parser.add_argument(
        "--execute", action="store_true", help="write the row (--inactive is a dry run otherwise)"
    )
    arguments = parser.parse_args()
    if not arguments.inactive:
        if arguments.version or arguments.execute:
            parser.error("--version and --execute require --inactive")
        print(f"Serving model id: {register_serving_model()}")
    else:
        if not arguments.version:
            parser.error("--inactive requires --version")
        model_id, created = register_inactive_model(arguments.version, execute=arguments.execute)
        if model_id is None:
            print(f"Dry run: model {arguments.version} would be registered inactive")
        else:
            state = "Registered inactive" if created else "Already registered"
            print(f"{state}: model {arguments.version} id {model_id}")
