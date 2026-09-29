import type { ActiveModel } from "../api/client";
import type { Resource } from "../hooks/useDashboard";
import type { Translate } from "../i18n/translations";
import { InfoTip } from "./InfoTip";
import { Skeleton } from "./Skeleton";

type HeroProps = {
  t: Translate;
  model: Resource<ActiveModel | null>;
};

export function Hero({ t, model }: HeroProps) {
  const loading = model.status === "loading";
  return (
    <section className="hero container" aria-labelledby="hero-title">
      <div className="hero-copy">
        <h1 id="hero-title">{t("heroTitle")}</h1>
        <p className="lede">{t("heroLead")}</p>
        <div className="button-row">
          <a className="btn btn-primary" href="#forecast">
            {t("heroCta")}
          </a>
          <a className="btn btn-ghost" href="#analysis">
            {t("heroCtaSecondary")}
          </a>
        </div>
      </div>

      <aside className="model-card" aria-busy={loading} aria-label={t("activeModel")}>
        <div className="card-head">
          <span className="eyebrow">{t("activeModel")}</span>
          <InfoTip text={t("activeModelTooltip")} label={t("moreInfo")} align="end" />
        </div>
        {loading ? (
          <div className="model-body">
            <Skeleton width="80%" height={28} />
            <Skeleton width="45%" />
          </div>
        ) : model.data ? (
          <div className="model-body">
            <p className="model-name">{model.data.name}</p>
            <dl className="meta-list">
              <div>
                <dt>{t("modelVersion")}</dt>
                <dd>v{model.data.version}</dd>
              </div>
              <div>
                <dt>{t("modelHorizon")}</dt>
                <dd>H+{model.data.horizon}</dd>
              </div>
            </dl>
          </div>
        ) : (
          <p className="model-name muted">{t("unavailable")}</p>
        )}
      </aside>
    </section>
  );
}
