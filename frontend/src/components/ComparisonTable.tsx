import type { ActiveModel, Prediction } from "../api/client";
import type { Resource } from "../hooks/useDashboard";
import type { Translate } from "../i18n/translations";
import { getAbsoluteError, getMatchWithActual } from "../lib/format";
import type { Formatters } from "../lib/format";
import { COMPARISON_ROWS, sortNewestFirst } from "../lib/predictions";
import { InfoTip } from "./InfoTip";
import { SkeletonRows } from "./Skeleton";
import { SplitBadge } from "./SplitBadge";

type ComparisonTableProps = {
  t: Translate;
  fmt: Formatters;
  predictions: Resource<Prediction[]>;
  total: number;
  model: ActiveModel | null;
  focusDate: string | null;
  onFocus: (date: string) => void;
};

export function ComparisonTable({ t, fmt, predictions, total, model, focusDate, onFocus }: ComparisonTableProps) {
  const loading = predictions.status === "loading";
  const rows = sortNewestFirst(predictions.data).slice(0, COMPARISON_ROWS);
  return (
    <div aria-busy={loading}>
      <div className="section-head">
        <div>
          <span className="eyebrow">{t("predictionVsActual")}</span>
          <h2>{t("historicalComparison")}</h2>
        </div>
        <div className="card-meta">
          <InfoTip text={t("comparisonTooltip")} label={t("moreInfo")} align="end" />
          <span className="muted">
            {loading ? "…" : total} {t("recordCount")}
          </span>
        </div>
      </div>
      <p className="hint split-note">{t("splitNote")}</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t("date")}</th>
              <th scope="col">{t("predicted")}</th>
              <th scope="col">{t("actual")}</th>
              <th scope="col">{t("absError")}</th>
              <th scope="col">{t("matchWithActual")}</th>
              <th scope="col">{t("model")}</th>
            </tr>
          </thead>
          <tbody>
            {loading && <SkeletonRows rows={5} columns={6} />}
            {!loading &&
              rows.map((item, index) => {
                const absError = getAbsoluteError(item.actual_demand_kwh, item.predicted_demand_kwh);
                const match = getMatchWithActual(item.actual_demand_kwh, item.predicted_demand_kwh);
                const version = model && item.model_id === model.id ? `v${model.version}` : `${t("model")} ${item.model_id.slice(0, 8)}`;
                const focused = item.target_date === focusDate;
                return (
                  <tr key={item.id} className={focused ? "is-focused" : ""}>
                    <td>
                      <button
                        type="button"
                        className="row-button"
                        aria-current={focused ? "true" : undefined}
                        onClick={() => onFocus(item.target_date)}
                      >
                        {fmt.date(item.target_date)}
                      </button>
                      <span className="badge-group">
                        {index === 0 && <span className="tag row-badge">{t("currentForecast")}</span>}
                        <SplitBadge t={t} targetDate={item.target_date} modelVersion={item.model_version ?? (model && item.model_id === model.id ? model.version : undefined)} />
                      </span>
                    </td>
                    <td className="num">{fmt.kwh(item.predicted_demand_kwh)}</td>
                    <td className="num">{fmt.kwh(item.actual_demand_kwh)}</td>
                    <td className="num">{fmt.kwh(absError)}</td>
                    <td className="num">{fmt.percent(match)}</td>
                    <td>{version}</td>
                  </tr>
                );
              })}
            {predictions.status === "error" && !rows.length && (
              <tr>
                <td colSpan={6} className="empty">
                  {t("backendUnavailable")}
                </td>
              </tr>
            )}
            {!loading && predictions.status !== "error" && !rows.length && (
              <tr>
                <td colSpan={6} className="empty">
                  {t("noStoredPredictions")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
