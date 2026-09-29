import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api/client";
import type { ActiveModel, Demand, Prediction } from "../api/client";
import type { Translate } from "../i18n/translations";
import { addDays, getDateValidationMessage, isWithinDataRange } from "../lib/format";
import { WINDOW_DAYS } from "../lib/chart";

export type Health = "checking" | "online" | "offline";
export type Resource<T> = { status: "loading" | "ready" | "error"; data: T };
export type ContextData = { demand: Demand[]; predictions: Prediction[] };

const DEFAULT_TARGET_DATE = "2023-01-03";

function describeError(reason: unknown, t: Translate, fallback: "backendUnavailable" | "predictionUnavailable"): string {
  if (reason instanceof ApiError && reason.status > 0) return reason.message;
  return t(fallback);
}

function mostRecentlyStored(predictions: Prediction[]): Prediction | null {
  return predictions.reduce<Prediction | null>(
    (latest, item) => (latest === null || item.created_at > latest.created_at ? item : latest),
    null,
  );
}

/** Container hook: owns every request and exposes loading state per resource. */
export function useDashboard(t: Translate) {
  const [health, setHealth] = useState<Health>("checking");
  const [model, setModel] = useState<Resource<ActiveModel | null>>({ status: "loading", data: null });
  const [predictions, setPredictions] = useState<Resource<Prediction[]>>({ status: "loading", data: [] });
  const [totalStored, setTotalStored] = useState(0);
  const [context, setContext] = useState<Resource<ContextData>>({
    status: "loading",
    data: { demand: [], predictions: [] },
  });
  const [targetDate, setTargetDate] = useState(DEFAULT_TARGET_DATE);
  const [latest, setLatest] = useState<Prediction | null>(null);
  const [focusOverride, setFocusOverride] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState("");

  const dateIssue = getDateValidationMessage(targetDate, t);

  const loadPredictions = useCallback(async () => {
    try {
      const result = await api.recentPredictions();
      setPredictions({ status: "ready", data: [...result.items].sort((a, b) => b.target_date.localeCompare(a.target_date)) });
      setTotalStored(result.total);
    } catch {
      setPredictions((previous) => ({ status: "error", data: previous.data }));
    }
  }, []);

  useEffect(() => {
    api
      .health()
      .then((response) => setHealth(response.status === "ok" ? "online" : "offline"))
      .catch(() => setHealth("offline"));
    api
      .activeModel()
      .then((data) => setModel({ status: "ready", data }))
      .catch(() => setModel({ status: "error", data: null }));
    void loadPredictions();
  }, [loadPredictions]);

  const focusDate = useMemo<string | null>(() => {
    if (focusOverride) return focusOverride;
    if (predictions.status === "loading") return null;
    const stored = mostRecentlyStored(predictions.data);
    if (stored) return stored.target_date;
    return isWithinDataRange(targetDate) ? targetDate : null;
  }, [focusOverride, predictions, targetDate]);

  const waitingForFocus = focusDate === null && predictions.status === "loading";

  useEffect(() => {
    if (focusDate === null) {
      setContext({ status: waitingForFocus ? "loading" : "ready", data: { demand: [], predictions: [] } });
      return;
    }
    let cancelled = false;
    const start = addDays(focusDate, -WINDOW_DAYS);
    setContext({ status: "loading", data: { demand: [], predictions: [] } });
    Promise.all([api.demandInRange(start, focusDate), api.predictionsInRange(start, focusDate)])
      .then(([demand, stored]) => {
        if (!cancelled) setContext({ status: "ready", data: { demand, predictions: stored } });
      })
      .catch(() => {
        if (!cancelled) setContext({ status: "error", data: { demand: [], predictions: [] } });
      });
    return () => {
      cancelled = true;
    };
  }, [focusDate, waitingForFocus]);

  const focusPrediction = useMemo<Prediction | null>(() => {
    if (!focusDate) return null;
    if (latest?.target_date === focusDate) return latest;
    return (
      context.data.predictions.find((item) => item.target_date === focusDate) ??
      predictions.data.find((item) => item.target_date === focusDate) ??
      null
    );
  }, [focusDate, latest, context.data.predictions, predictions.data]);

  async function createPrediction() {
    if (dateIssue) {
      setNotice(dateIssue);
      return;
    }
    setSubmitting(true);
    setNotice("");
    try {
      const prediction = await api.createPrediction(targetDate);
      setLatest(prediction);
      setFocusOverride(prediction.target_date);
      await loadPredictions();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        setFocusOverride(targetDate);
        setNotice(t("predictionExists"));
      } else {
        setNotice(describeError(reason, t, "predictionUnavailable"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return {
    health,
    model,
    predictions,
    totalStored,
    context,
    targetDate,
    setTargetDate,
    dateIssue,
    latest,
    focusDate,
    focusPrediction,
    setFocusDate: setFocusOverride,
    submitting,
    notice,
    dismissNotice: () => setNotice(""),
    createPrediction,
  };
}
