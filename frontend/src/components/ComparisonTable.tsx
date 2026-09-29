import type { ActiveModel, Prediction } from "../api/client";
import type { Resource } from "../hooks/useDashboard";
import type { Translate } from "../i18n/translations";
import { getAbsoluteError, getMatchWithActual } from "../lib/format";
import type { Formatters } from "../lib/format";
import { InfoTip } from "./InfoTip";
import { SkeletonRows } from "./Skeleton";

type ComparisonTableProps = {
  t: Translate;
  fmt: Formatters;
  predictions: Resource<Prediction[]>;
  total: number;
  model: ActiveModel | null;
  focusDate: string | null;
  onFocus: (date: string) => void;
};

const ROWS = 8;

export function ComparisonTable({ t, fmt, predictions, total, model, focusDate, onFocus }: ComparisonTableProps) {
  const loading = predictions.status === "loading";
  const rows = predictions.data.slice(0, ROWS);
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
              rows.map((item) => {
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
                    </td>
                    <td className="num">{fmt.kwh(item.predicted_demand_kwh)}</td>
                    <td className="num">{fmt.kwh(item.actual_demand_kwh)}</td>
                    <td className="num">{fmt.kwh(absError)}</td>
                    <td className="num">{fmt.percent(match)}</td>
                    <td>{version}</td>
                  </tr>
                );
              })}
            {!loading && !rows.length && (
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
