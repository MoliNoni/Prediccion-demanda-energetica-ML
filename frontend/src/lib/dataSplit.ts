export type DataSplit = "train" | "validation" | "test";

export type SplitPeriods = {
  trainStart: number;
  trainEnd: number;
  /** Last validation year, or null when the model has no validation period. */
  validationEnd: number | null;
  testStart: number;
  testEnd: number;
};

const FIRST_YEAR = 2000;
const LAST_YEAR = 2023;

const SEALED_TEST: SplitPeriods = {
  trainStart: FIRST_YEAR,
  trainEnd: 2019,
  validationEnd: 2021,
  testStart: 2022,
  testEnd: LAST_YEAR,
};

// From data/processed/modeling_run_metadata.json and the serving_model_v*_metadata.json "periods".
// v1.2.0 keeps the same evaluation protocol but its deployed model was refit on 2000-2021, so it has no validation period.
const PERIODS_BY_VERSION = new Map<string, SplitPeriods>([
  ["1.0.0", SEALED_TEST],
  ["1.1.0", SEALED_TEST],
  ["1.2.0", { ...SEALED_TEST, trainEnd: 2021, validationEnd: null }],
]);

/** Model versions retired from the dashboard comparisons. */
export const RETIRED_MODEL_VERSIONS = ["1.0.0"];

/** Accepts "1.2.0" or "v1.2.0"; unknown or missing versions return null so no period is claimed for them. */
export function splitPeriodsFor(modelVersion?: string | null): SplitPeriods | null {
  const version = (modelVersion ?? "").trim().replace(/^v/i, "");
  return PERIODS_BY_VERSION.get(version) ?? null;
}

export function dataSplitFor(targetDate: string, modelVersion?: string | null): DataSplit | null {
  const year = Number.parseInt(targetDate.slice(0, 4), 10);
  const periods = splitPeriodsFor(modelVersion);
  if (periods === null || Number.isNaN(year)) return null;
  if (year <= periods.trainEnd) return "train";
  if (periods.validationEnd !== null && year <= periods.validationEnd) return "validation";
  return "test";
}
