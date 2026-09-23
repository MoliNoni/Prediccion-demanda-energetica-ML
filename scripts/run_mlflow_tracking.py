from tracking.mlflow_tracking import track_existing_results

if __name__ == "__main__":
    run_id = track_existing_results()
    print(f"MLflow run: {run_id}")
    print("Tracking directory: mlruns")
