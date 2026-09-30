import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import type { Prediction } from "../api/client";
import type { ContextData, Resource } from "../hooks/useDashboard";
import type { Translate } from "../i18n/translations";
import { WINDOW_DAYS, buildBrokenPath, buildContextSeries, niceTicks } from "../lib/chart";
import type { ContextSeries } from "../lib/chart";
import { getRelativeError } from "../lib/format";
import { RETIRED_MODEL_VERSIONS, splitPeriodsFor } from "../lib/dataSplit";
import type { Formatters } from "../lib/format";
import { addDays } from "../lib/format";
import { InfoTip } from "./InfoTip";
import { Skeleton } from "./Skeleton";

type PredictionContextChartProps = {
  t: Translate;
  fmt: Formatters;
  focusDate: string | null;
  context: Resource<ContextData>;
  focusPrediction: Prediction | null;
  /** True when the focused prediction is the most recently generated one. */
  isLatest: boolean;
};

const MARGIN = { top: 16, right: 22, bottom: 30, left: 48 };
const TICK_EVERY_DAYS = 14;
const TOOLTIP_WIDTH = 176;
const GWH = 1e6;

/** Only versions with a known split are compared, and retired ones are hidden. */
function isShownModelVersion(version?: string | null): boolean {
  const normalized = (version ?? "").trim().replace(/^v/i, "");
  return splitPeriodsFor(normalized) !== null && !RETIRED_MODEL_VERSIONS.includes(normalized);
}

export function PredictionContextChart({ t, fmt, focusDate, context, focusPrediction, isLatest }: PredictionContextChartProps) {
  // Stored markers are the forecasts of the other, non-retired models; the focused model's own are not drawn.
  const otherModelPredictions = useMemo(
    () =>
      focusPrediction
        ? context.data.predictions.filter((item) => item.model_id !== focusPrediction.model_id && isShownModelVersion(item.model_version))
        : [],
    [context, focusPrediction],
  );
  const series = useMemo(
    () =>
      focusDate && context.status === "ready"
        ? buildContextSeries(focusDate, context.data.demand, otherModelPredictions, focusPrediction)
        : null,
    [focusDate, context, otherModelPredictions, focusPrediction],
  );
  const hasActuals = series?.days.some((day) => day.actual !== null) ?? false;
  const loading = context.status === "loading";

  return (
    <div className="container">
      <div className="section-head">
        <div>
          <span className="eyebrow">{t("contextEyebrow")}</span>
          <h2>
            {isLatest && focusPrediction?.model_version
              ? t("contextTitleLatest", { version: focusPrediction.model_version })
              : t("contextTitle")}
          </h2>
        </div>
        <InfoTip text={t("contextTooltip")} label={t("moreInfo")} align="end" />
      </div>

      <figure className="card card-data chart-card" aria-busy={loading}>
        {loading && <Skeleton variant="block" className="chart-skeleton" />}
        {context.status === "error" && <p className="empty">{t("contextUnavailable")}</p>}
        {context.status === "ready" && !series && <p className="empty">{t("contextEmpty")}</p>}
        {series && !hasActuals && <p className="empty">{t("contextNoData")}</p>}
        {series && hasActuals && <ChartBody t={t} fmt={fmt} series={series} />}

        {!loading && series && <StatRow t={t} fmt={fmt} series={series} />}
        {!loading && !focusPrediction && context.status === "ready" && <p className="hint">{t("contextEmpty")}</p>}
      </figure>
    </div>
  );
}

function StatRow({ t, fmt, series }: { t: Translate; fmt: Formatters; series: ContextSeries }) {
  const { predictedAtFocus: predicted, actualAtFocus: actual, baseline } = series;
  const error = predicted !== null && actual !== null ? getRelativeError(actual, predicted) : null;
  const versusAverage = predicted !== null && baseline ? ((predicted - baseline) / baseline) * 100 : null;
  const stats: Array<[string, string]> = [
    [t("statPredicted"), fmt.gwh(predicted, 2)],
    [t("statActual"), fmt.gwh(actual, 2)],
    [t("statError"), fmt.percent(error)],
    [t("statVsAverage"), fmt.percent(versusAverage, 1, true)],
  ];
  return (
    <dl className="stat-row">
      {stats.map(([label, value]) => (
        <div className="stat" key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ChartBody({ t, fmt, series }: { t: Translate; fmt: Formatters; series: ContextSeries }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    const element = frameRef.current;
    if (!element) return;
    setWidth(Math.max(280, Math.floor(element.clientWidth)));
    const observer = new ResizeObserver((entries) => {
      const next = Math.floor(entries[0].contentRect.width);
      if (next > 0) setWidth(Math.max(280, next));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const height = width < 480 ? 260 : 320;
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const scale = useMemo(() => {
    const values: number[] = [];
    for (const day of series.days) {
      for (const value of [day.actual, day.average, day.stored]) if (value !== null) values.push(value / GWH);
    }
    if (series.predictedAtFocus !== null) values.push(series.predictedAtFocus / GWH);
    const { ticks, step } = niceTicks(Math.min(...values), Math.max(...values), 4);
    return { ticks, step, min: ticks[0], max: ticks[ticks.length - 1] };
  }, [series]);

  const x = (index: number) => MARGIN.left + (index / WINDOW_DAYS) * plotWidth;
  const y = (kwh: number) => MARGIN.top + (1 - (kwh / GWH - scale.min) / (scale.max - scale.min)) * plotHeight;
  const yOrNull = (value: number | null) => (value === null ? null : y(value));

  const actualPath = buildBrokenPath(series.days.slice(0, WINDOW_DAYS).map((day) => ({ x: x(day.index), y: yOrNull(day.actual) })));
  const averagePath = buildBrokenPath(series.days.slice(0, WINDOW_DAYS).map((day) => ({ x: x(day.index), y: yOrNull(day.average) })));
  const tickDigits = scale.step >= 1 ? 0 : scale.step >= 0.1 ? 1 : 2;

  const xTicks: number[] = [];
  for (let index = WINDOW_DAYS; index >= 0; index -= TICK_EVERY_DAYS) xTicks.push(index);

  const { predictedAtFocus, actualAtFocus, lastActualIndex } = series;
  const lastActual = lastActualIndex === null ? null : series.days[lastActualIndex].actual;
  const activeDay = active === null ? null : series.days[active];
  const activePredicted = activeDay ? (activeDay.index === WINDOW_DAYS ? predictedAtFocus : activeDay.stored) : null;

  function moveTo(clientX: number, element: SVGSVGElement) {
    const rect = element.getBoundingClientRect();
    const raw = ((clientX - rect.left - MARGIN.left) / plotWidth) * WINDOW_DAYS;
    setActive(Math.min(WINDOW_DAYS, Math.max(0, Math.round(raw))));
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const current = active ?? WINDOW_DAYS;
    const moves: Record<string, number> = {
      ArrowLeft: Math.max(0, current - 1),
      ArrowRight: Math.min(WINDOW_DAYS, current + 1),
      Home: 0,
      End: WINDOW_DAYS,
    };
    if (event.key in moves) {
      event.preventDefault();
      setActive(moves[event.key]);
    }
  }

  const tooltipLeft = activeDay
    ? Math.min(Math.max(x(activeDay.index) - TOOLTIP_WIDTH / 2, 0), Math.max(0, width - TOOLTIP_WIDTH))
    : 0;
  const tooltipText = activeDay
    ? [
        `${t("tipDate")} ${fmt.date(activeDay.date)}`,
        `${t("tipActual")} ${fmt.gwh(activeDay.index === WINDOW_DAYS ? actualAtFocus : activeDay.actual, 2)}`,
        `${t("tipAverage")} ${fmt.gwh(activeDay.index === WINDOW_DAYS ? series.baseline : activeDay.average, 2)}`,
        ...(activePredicted !== null ? [`${t("tipPredicted")} ${fmt.gwh(activePredicted, 2)}`] : []),
      ]
    : [];

  return (
    <>
      <div
        className="chart-frame"
        ref={frameRef}
        tabIndex={0}
        role="group"
        aria-label={`${t("chartLabel")}. ${t("chartKeyboardHint")}`}
        onKeyDown={onKeyDown}
        onFocus={() => setActive((value) => value ?? WINDOW_DAYS)}
        onBlur={() => setActive(null)}
      >
        <p className="axis-unit">{t("chartAxisUnit")}</p>
        <svg
          width={width}
          height={height}
          aria-hidden="true"
          onPointerMove={(event: PointerEvent<SVGSVGElement>) => moveTo(event.clientX, event.currentTarget)}
          onPointerLeave={() => setActive(null)}
        >
          {scale.ticks.map((tick) => (
            <g key={tick}>
              <line className="grid-line" x1={MARGIN.left} x2={width - MARGIN.right} y1={y(tick * GWH)} y2={y(tick * GWH)} />
              <text className="axis-label" x={MARGIN.left - 8} y={y(tick * GWH)} textAnchor="end" dominantBaseline="middle">
                {fmt.axisNumber(tick, tickDigits)}
              </text>
            </g>
          ))}
          {xTicks.map((index) => (
            <text
              key={index}
              className="axis-label"
              x={x(index)}
              y={height - 8}
              textAnchor={index === WINDOW_DAYS ? "end" : "middle"}
            >
              {fmt.shortDate(addDays(series.focusDate, index - WINDOW_DAYS))}
            </text>
          ))}

          <path className="line-average" d={averagePath} />
          <path className="line-actual" d={actualPath} />

          {series.days
            .filter((day) => day.stored !== null && day.index < WINDOW_DAYS)
            .map((day) => (
              <circle key={day.date} className="marker-stored" cx={x(day.index)} cy={y(day.stored as number)} r={3.5} />
            ))}

          {predictedAtFocus !== null && lastActual !== null && lastActualIndex !== null && (
            <line
              className="line-step"
              x1={x(lastActualIndex)}
              y1={y(lastActual)}
              x2={x(WINDOW_DAYS)}
              y2={y(predictedAtFocus)}
            />
          )}
          {actualAtFocus !== null && <circle className="marker-actual" cx={x(WINDOW_DAYS)} cy={y(actualAtFocus)} r={4} />}
          {predictedAtFocus !== null && <circle className="marker-predicted" cx={x(WINDOW_DAYS)} cy={y(predictedAtFocus)} r={5} />}

          {activeDay && (
            <line className="crosshair" x1={x(activeDay.index)} x2={x(activeDay.index)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} />
          )}
        </svg>

        {activeDay && (
          <div className="chart-tooltip" style={{ left: tooltipLeft, width: TOOLTIP_WIDTH }} aria-hidden="true">
            {tooltipText.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </div>
        )}
        <p className="sr-only" aria-live="polite">
          {tooltipText.join(", ")}
        </p>
      </div>

      <ul className="legend">
        <li>
          <svg width="22" height="8" aria-hidden="true">
            <line className="line-actual" x1="0" x2="22" y1="4" y2="4" />
          </svg>
          {t("legendActual")}
        </li>
        <li>
          <svg width="22" height="8" aria-hidden="true">
            <line className="line-average" x1="0" x2="22" y1="4" y2="4" />
          </svg>
          {t("legendAverage")}
        </li>
        <li>
          <svg width="12" height="12" aria-hidden="true">
            <circle className="marker-predicted" cx="6" cy="6" r="5" />
          </svg>
          {t("legendPredicted")}
        </li>
        <li>
          <svg width="12" height="12" aria-hidden="true">
            <circle className="marker-stored" cx="6" cy="6" r="3.5" />
          </svg>
          {t("legendStored")}
        </li>
      </ul>
    </>
  );
}
