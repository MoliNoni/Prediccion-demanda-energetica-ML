import type { Prediction } from "../api/client";
import type { Resource } from "../hooks/useDashboard";
import type { Translate } from "../i18n/translations";
import type { Formatters } from "../lib/format";
import { InfoTip } from "./InfoTip";
import { SkeletonRows } from "./Skeleton";

type PredictionLedgerProps = {
  t: Translate;
  fmt: Formatters;
  predictions: Resource<Prediction[]>;
  total: number;
  focusDate: string | null;
  onFocus: (date: string) => void;
};

const ROWS = 8;

export function PredictionLedger({ t, fmt, predictions, total, focusDate, onFocus }: PredictionLedgerProps) {
  const loading = predictions.status === "loading";
  const rows = predictions.data.slice(0, ROWS);
  return (
    <div className="card card-data" aria-busy={loading}>
      <div className="card-head">
        <div>
          <span className="eyebrow">{t("storedPredictions")}</span>
          <h3>{t("forecastLedger")}</h3>
        </div>
        <div className="card-meta">
          <InfoTip text={t("predictionsTooltip")} label={t("moreInfo")} align="end" />
          <span className="tag">{loading ? "…" : total}</span>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t("date")}</th>
              <th scope="col">{t("predicted")}</th>
              <th scope="col">{t("actual")}</th>
            </tr>
          </thead>
          <tbody>
            {loading && <SkeletonRows rows={5} columns={3} />}
            {!loading &&
              rows.map((item) => (
                <tr key={item.id} className={item.target_date === focusDate ? "is-focused" : ""}>
                  <td>
                    <button
                      type="button"
                      className="row-button"
                      aria-current={item.target_date === focusDate ? "true" : undefined}
                      onClick={() => onFocus(item.target_date)}
                    >
                      {fmt.date(item.target_date)}
                    </button>
                  </td>
                  <td className="num">{fmt.kwh(item.predicted_demand_kwh)}</td>
                  <td className="num">{fmt.kwh(item.actual_demand_kwh)}</td>
                </tr>
              ))}
            {!loading && !rows.length && (
              <tr>
                <td colSpan={3} className="empty">
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
