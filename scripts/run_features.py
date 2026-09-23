from features.pipeline import FEATURE_OUTPUT, build_feature_dataset

if __name__ == "__main__":
    result = build_feature_dataset()
    print(f"Input rows processed into features: {len(result)}")
    print(f"Output: {FEATURE_OUTPUT}")
