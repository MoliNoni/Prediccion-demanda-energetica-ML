import type { Prediction } from "../api/client";

/** Rows shown in the "prediction vs actual" table, also the size of the newest-generated fetch. */
export const COMPARISON_ROWS = 8;

/** Newest generated first (created_at), then latest target date, so the order is deterministic. */
export function compareNewestFirst(a: Prediction, b: Prediction): number {
  return b.created_at.localeCompare(a.created_at) || b.target_date.localeCompare(a.target_date);
}

export function sortNewestFirst(predictions: Prediction[]): Prediction[] {
  return [...predictions].sort(compareNewestFirst);
}

/** The most recently generated prediction, or null when there are none. */
export function latestGenerated(predictions: Prediction[]): Prediction | null {
  return sortNewestFirst(predictions)[0] ?? null;
}
