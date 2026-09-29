import type { Demand, Prediction } from "../api/client";
import { addDays } from "./format";

export const WINDOW_DAYS = 60;
const AVERAGE_DAYS = 7;
const MIN_AVERAGE_SAMPLES = 4;

export type ContextDay = {
  date: string;
  /** 0 is the first day of the window, WINDOW_DAYS is the focused date. */
  index: number;
  actual: number | null;
  average: number | null;
  /** Stored prediction for this day, when one exists. */
  stored: number | null;
};

export type ContextSeries = {
  days: ContextDay[];
  focusDate: string;
  focusIndex: number;
  actualAtFocus: number | null;
  predictedAtFocus: number | null;
  /** Mean of the seven days before the focused date. */
  baseline: number | null;
  /** Last day before the focused date that has an actual value. */
  lastActualIndex: number | null;
};

function mean(values: number[]): number | null {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

export function buildContextSeries(
  focusDate: string,
  demand: Demand[],
  predictions: Prediction[],
  focusPrediction: Prediction | null,
): ContextSeries {
  const actualByDate = new Map(demand.map((item) => [item.date, item.demand_kwh]));
  const storedByDate = new Map(predictions.map((item) => [item.target_date, item.predicted_demand_kwh]));
  const days: ContextDay[] = [];

  for (let index = 0; index <= WINDOW_DAYS; index += 1) {
    const date = addDays(focusDate, index - WINDOW_DAYS);
    days.push({
      date,
      index,
      actual: actualByDate.get(date) ?? null,
      average: null,
      stored: storedByDate.get(date) ?? null,
    });
  }

  for (const day of days) {
    if (day.index >= WINDOW_DAYS || day.actual === null) continue;
    const window = days
      .slice(Math.max(0, day.index - AVERAGE_DAYS + 1), day.index + 1)
      .map((item) => item.actual)
      .filter((value): value is number => value !== null);
    day.average = window.length >= MIN_AVERAGE_SAMPLES ? mean(window) : null;
  }

  const baselineSamples = days
    .slice(WINDOW_DAYS - AVERAGE_DAYS, WINDOW_DAYS)
    .map((item) => item.actual)
    .filter((value): value is number => value !== null);

  let lastActualIndex: number | null = null;
  for (let index = WINDOW_DAYS - 1; index >= 0; index -= 1) {
    if (days[index].actual !== null) {
      lastActualIndex = index;
      break;
    }
  }

  return {
    days,
    focusDate,
    focusIndex: WINDOW_DAYS,
    actualAtFocus: days[WINDOW_DAYS].actual,
    predictedAtFocus: focusPrediction?.predicted_demand_kwh ?? days[WINDOW_DAYS].stored,
    baseline: baselineSamples.length >= MIN_AVERAGE_SAMPLES ? mean(baselineSamples) : null,
    lastActualIndex,
  };
}

/** Builds an SVG path that restarts (M) after every missing value, so gaps are never bridged. */
export function buildBrokenPath(points: Array<{ x: number; y: number | null }>): string {
  let path = "";
  let penDown = false;
  for (const point of points) {
    if (point.y === null) {
      penDown = false;
      continue;
    }
    path += `${penDown ? "L" : "M"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    penDown = true;
  }
  return path;
}

export function niceTicks(min: number, max: number, target = 4): { ticks: number[]; step: number } {
  const span = Math.max(max - min, Math.abs(max) * 0.02, 1e-9);
  const raw = span / (target - 1);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = start; value <= end + step / 2; value += step) {
    ticks.push(Number(value.toFixed(6)));
  }
  return { ticks, step };
}
