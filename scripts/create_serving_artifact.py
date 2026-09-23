from models.serving import create_serving_artifact

if __name__ == "__main__":
    metadata = create_serving_artifact()
    print(f"MLflow run: {metadata['run_id']}")
    print(f"Model URI: {metadata['model_uri']}")
