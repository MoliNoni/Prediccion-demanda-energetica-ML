from evaluation.run_evaluation_v2 import run_evaluation_v2
from features.pipeline import build_feature_dataset_v2
from models.serving_v2 import create_candidate_serving_artifact_v2
from models.training_v2 import run_modeling_v2

if __name__ == "__main__":
    features = build_feature_dataset_v2()
    predictions, _ = run_modeling_v2()
    evaluation = run_evaluation_v2()
    artifact = create_candidate_serving_artifact_v2()
    print(f"V2 feature rows: {len(features)}")
    print(f"V2 prediction rows: {len(predictions)}")
    print(f"V2 Validation/Test comparisons: {len(evaluation['results'])}")
    print(f"Candidate MLflow run: {artifact['run_id']}")
