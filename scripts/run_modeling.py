from models.training import PREDICTIONS_OUTPUT, run_modeling

if __name__ == "__main__":
    predictions, metadata = run_modeling()
    print(f"Training records: {metadata['train_records']}")
    print(f"Validation predictions: {(predictions['split'] == 'validation').sum()}")
    print(f"Test predictions: {(predictions['split'] == 'test').sum()}")
    print(f"Output: {PREDICTIONS_OUTPUT}")
