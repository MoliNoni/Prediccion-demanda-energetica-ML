import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type { ActiveModel, Demand, Prediction } from "../api/client";
import type { Translate } from "../i18n/translations";
import { addDays, getDateValidationMessage, isWithinDataRange } from "../lib/format";
import { WINDOW_DAYS } from "../lib/chart";
import { COMPARISON_ROWS, latestGenerated } from "../lib/predictions";

export type Health = "checking" | "online" | "offline";
export type Resource<T> = { status: "loading" | "ready" | "error"; data: T };
export type ContextData = { demand: Demand[]; predictions: Prediction[] };

const DEFAULT_TARGET_DATE = "2023-01-03";

function describeError(reason: unknown, t: Translate, fallback: "backendUnavailable" | "predictionUnavailable"): string {
  if (reason instanceof ApiError && reason.status > 0) return reason.message;
  return t(fallback);
}

/** Container hook: owns every request and exposes loading state per resource. */
export function useDashboard(t: Translate) {
  const [health, setHealth] = useState<Health>("checking");
  const [model, setModel] = useState<Resource<ActiveModel | null>>({ status: "loading", data: null });
  const [predictions, setPredictions] = useState<Resource<Prediction[]>>({ status: "loading", data: [] });
  const [newest, setNewest] = useState<Resource<Prediction[]>>({ status: "loading", data: [] });
  const [totalStored, setTotalStored] = useState(0);
  const [context, setContext] = useState<Resource<ContextData>>({
    status: "loading",
    data: { demand: [], predictions: [] },
  });
  const [focusCandidates, setFocusCandidates] = useState<Prediction[]>([]);
  const [targetDate, setTargetDate] = useState(DEFAULT_TARGET_DATE);
  const [latest, setLatest] = useState<Prediction | null>(null);
  const [focusOverride, setFocusOverride] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState("");

  const dateIssue = getDateValidationMessage(targetDate, t);

  // Only the response to the most recent load may update state; older ones are dropped.
  const loadSequence = useRef(0);

  const loadPredictions = useCallback(async () => {
    const sequence = ++loadSequence.current;
    const isCurrent = () => sequence === loadSequence.current;
    api
      .newestPredictions(COMPARISON_ROWS)
      .then((items) => {
        if (isCurrent()) setNewest({ status: "ready", data: items });
      })
      .catch(() => {
        if (isCurrent()) setNewest((previous) => ({ status: "error", data: previous.data }));
      });
    try {
      const result = await api.recentPredictions();
      if (!isCurrent()) return;
      setPredictions({ status: "ready", data: [...result.items].sort((a, b) => b.target_date.localeCompare(a.target_date)) });
      setTotalStored(result.total);
    } catch {
      if (isCurrent()) setPredictions((previous) => ({ status: "error", data: previous.data }));
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

  // Falls back to the target_date-loaded list when the newest-generated request failed.
  const latestSource = newest.status === "error" ? predictions : newest;
  const latestStored = useMemo(() => latestGenerated(latestSource.data), [latestSource]);

  const focusDate = useMemo<string | null>(() => {
    if (focusOverride) return focusOverride;
    if (latestSource.status === "loading") return null;
    if (latestStored) return latestStored.target_date;
    return isWithinDataRange(targetDate) ? targetDate : null;
  }, [focusOverride, latestSource, latestStored, targetDate]);

  const waitingForFocus = focusDate === null && latestSource.status === "loading";

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

  // Every model's prediction for the focused date, so the context chart can switch between them.
  useEffect(() => {
    setFocusCandidates([]);
    if (focusDate === null) return;
    let cancelled = false;
    api
      .predictionsInRange(focusDate, focusDate)
      .then((items) => {
        if (!cancelled) setFocusCandidates(items.filter((item) => item.target_date === focusDate));
      })
      .catch(() => {
        if (!cancelled) setFocusCandidates([]);
      });
    return () => {
      cancelled = true;
    };
  }, [focusDate, latest]);

  const focusPrediction = useMemo<Prediction | null>(() => {
    if (!focusDate) return null;
    if (latest?.target_date === focusDate) return latest;
    return (
      context.data.predictions.find((item) => item.target_date === focusDate) ??
      newest.data.find((item) => item.target_date === focusDate) ??
      predictions.data.find((item) => item.target_date === focusDate) ??
      null
    );
  }, [focusDate, latest, context.data.predictions, newest.data, predictions.data]);

  const isLatestFocus = useMemo(
    () => focusPrediction !== null && focusPrediction.id === latestStored?.id,
    [focusPrediction, latestStored],
  );

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
    newest,
    totalStored,
    context,
    targetDate,
    setTargetDate,
    dateIssue,
    latest,
    focusDate,
    focusPrediction,
    focusCandidates,
    isLatestFocus,
    setFocusDate: setFocusOverride,
    submitting,
    notice,
    dismissNotice: () => setNotice(""),
    createPrediction,
  };
}
