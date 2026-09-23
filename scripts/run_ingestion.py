from ingestion.pipeline import run_ingestion

if __name__ == "__main__":
    audits = run_ingestion()
    print(f"Processed files: {len(audits)}")
    print("Output: data/interim/energy_demand_daily.parquet")
