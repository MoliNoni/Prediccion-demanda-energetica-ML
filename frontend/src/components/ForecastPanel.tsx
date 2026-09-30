import type { Prediction } from "../api/client";
import type { Translate } from "../i18n/translations";
import { splitPeriodsFor } from "../lib/dataSplit";
import { DATE_RANGE } from "../lib/format";
import type { Formatters } from "../lib/format";
import { InfoTip } from "./InfoTip";
import { SplitBadge } from "./SplitBadge";

type ForecastPanelProps = {
  t: Translate;
  fmt: Formatters;
  targetDate: string;
  dateIssue: string;
  submitting: boolean;
  latest: Prediction | null;
  modelVersion: string | null;
  activeVersion: string | null;
  onTargetDateChange: (value: string) => void;
  onSubmit: () => void;
};

export function ForecastPanel({
  t,
  fmt,
  targetDate,
  dateIssue,
  submitting,
  latest,
  modelVersion,
  activeVersion,
  onTargetDateChange,
  onSubmit,
}: ForecastPanelProps) {
  const rangeText = `${t("availableFrom")} ${fmt.date(DATE_RANGE.min)} ${t("to")} ${fmt.date(DATE_RANGE.max)}`;
  const periods = splitPeriodsFor(activeVersion);
  const splitTip = t(periods.validationEnd === null ? "splitTipTwoWay" : "splitTipThreeWay", {
    version: (activeVersion ?? "").replace(/^v/i, ""),
    trainFrom: String(periods.trainStart),
    trainTo: String(periods.trainEnd),
    validationFrom: String(periods.trainEnd + 1),
    validationTo: String(periods.validationEnd ?? periods.trainEnd),
    testFrom: String(periods.testStart),
    testTo: String(periods.testEnd),
  });
  return (
    <div className="card card-data forecast-panel">
      <div className="card-head">
        <div>
          <span className="eyebrow">{t("newPrediction")}</span>
          <h3>{t("chooseDate")}</h3>
        </div>
        <span className="tag">H+1</span>
      </div>

      <div className="field">
        <div className="field-label">
          <label htmlFor="target-date">{t("targetDate")}</label>
          <InfoTip text={t("selectorTooltip")} label={t("moreInfo")} />
        </div>
        <p className="hint" id="target-date-range">
          {rangeText}
        </p>
        <input
          id="target-date"
          type="date"
          min={DATE_RANGE.min}
          max={DATE_RANGE.max}
          value={targetDate}
          onChange={(event) => onTargetDateChange(event.target.value)}
          aria-invalid={Boolean(dateIssue)}
          aria-describedby="target-date-range target-date-feedback"
        />
        <p
          id="target-date-feedback"
          className={`feedback ${dateIssue ? "is-error" : ""}`}
          role={dateIssue ? "alert" : "status"}
          aria-live="polite"
        >
          {dateIssue || t("selectorReady")}
        </p>
      </div>

      <div className="action-row">
        <button type="button" className="btn btn-primary" onClick={onSubmit} disabled={submitting || !targetDate || Boolean(dateIssue)}>
          {submitting ? t("calculating") : t("runForecast")}
        </button>
        <InfoTip text={splitTip} label={t("moreInfo")} />
      </div>

      {latest && (
        <div className="result" aria-live="polite">
          <span className="eyebrow">{t("latestResult")}</span>
          <p className="result-value">{fmt.kwh(latest.predicted_demand_kwh)}</p>
          <p className="hint">
            {fmt.date(latest.target_date)} · {latest.model_version ? `v${latest.model_version}` : (modelVersion ?? t("model"))}
          </p>
          <p className="badge-group">
            <SplitBadge t={t} targetDate={latest.target_date} modelVersion={latest.model_version ?? activeVersion} />
          </p>
        </div>
      )}
    </div>
  );
}
