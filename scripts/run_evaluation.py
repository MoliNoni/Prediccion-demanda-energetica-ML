from evaluation.run_evaluation import run_evaluation

if __name__ == "__main__":
    result = run_evaluation()
    print(f"Selected model: {result['selected_model_by_validation']}")
    print("Output: data/processed/evaluation_results_h1.json")
