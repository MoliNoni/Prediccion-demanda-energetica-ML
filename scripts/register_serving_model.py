from database.repositories import ModelRepository
from database.session import create_database_engine
from models.serving import MODEL_HORIZON, MODEL_NAME, MODEL_VERSION, MlflowModelLoader


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


if __name__ == "__main__":
    print(f"Serving model id: {register_serving_model()}")
