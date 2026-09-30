export type DataSplit = "train" | "validation" | "test";

// Period boundaries from data/processed/modeling_run_metadata.json and serving_model_v2_metadata.json ("periods").
export const TRAIN_END_YEAR = 2019;
export const VALIDATION_END_YEAR = 2021;

export function dataSplitFor(targetDate: string): DataSplit {
  const year = Number.parseInt(targetDate.slice(0, 4), 10);
  if (year <= TRAIN_END_YEAR) return "train";
  if (year <= VALIDATION_END_YEAR) return "validation";
  return "test";
}
