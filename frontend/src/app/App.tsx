import { useEffect, useMemo, useState } from "react";
import { ComparisonTable } from "../components/ComparisonTable";
import { ForecastPanel } from "../components/ForecastPanel";
import { Header } from "../components/Header";
import { Hero } from "../components/Hero";
import { PowerBiReport } from "../components/PowerBiReport";
import { PredictionContextChart } from "../components/PredictionContextChart";
import { PredictionLedger } from "../components/PredictionLedger";
import { useDashboard } from "../hooks/useDashboard";
import { createTranslate } from "../i18n/translations";
import type { Language, TranslationKey } from "../i18n/translations";
import { createFormatters } from "../lib/format";
import { resolvePowerBiUrl } from "../lib/powerbi";

const LANGUAGE_KEY = "spde-language";
const POWERBI_URL = resolvePowerBiUrl(import.meta.env.VITE_POWERBI_EMBED_URL);

const DATA_SOURCES: Array<{ label: TranslationKey; href: string }> = [
  { label: "sourceXmDemand", href: "https://www.xm.com.co/consumo/informes-demanda" },
  { label: "sourceXmApi", href: "https://github.com/EquipoAnaliticaXM/API_XM" },
  { label: "sourceOni", href: "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php" },
];

function getInitialLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_KEY);
    if (stored === "es" || stored === "en") return stored;
  } catch {
    // Storage can be unavailable (private mode); fall back to the default.
  }
  return "es";
}

export function App() {
  const [lang, setLang] = useState<Language>(getInitialLanguage);
  const t = useMemo(() => createTranslate(lang), [lang]);
  const fmt = useMemo(() => createFormatters(lang, t), [lang, t]);
  const dashboard = useDashboard(t);

  useEffect(() => {
    try {
      window.localStorage.setItem(LANGUAGE_KEY, lang);
    } catch {
      // Ignore storage failures; the preference just will not persist.
    }
    document.documentElement.lang = lang;
  }, [lang]);

  const alert = dashboard.notice || (dashboard.health === "offline" ? t("backendUnavailable") : "");

  return (
    <div id="top">
      <Header t={t} lang={lang} health={dashboard.health} onLanguageChange={setLang} />

      {alert && (
        <div className="container">
          <p className="alert" role="alert">
            {alert}
          </p>
        </div>
      )}

      <main>
        <Hero t={t} model={dashboard.model} />

        <section id="forecast" className="band band-ash" aria-label={t("navForecast")}>
          <div className="container split">
            <ForecastPanel
              t={t}
              fmt={fmt}
              targetDate={dashboard.targetDate}
              dateIssue={dashboard.dateIssue}
              submitting={dashboard.submitting}
              latest={dashboard.latest}
              modelVersion={dashboard.model.data ? `v${dashboard.model.data.version}` : null}
              onTargetDateChange={dashboard.setTargetDate}
              onSubmit={() => void dashboard.createPrediction()}
            />
            <PredictionLedger
              t={t}
              fmt={fmt}
              predictions={dashboard.predictions}
              total={dashboard.totalStored}
              focusDate={dashboard.focusDate}
              onFocus={dashboard.setFocusDate}
            />
          </div>
        </section>

        <section className="band band-white" aria-label={t("predictionVsActual")}>
          <div className="container">
            <ComparisonTable
              t={t}
              fmt={fmt}
              predictions={dashboard.newest}
              total={dashboard.totalStored}
              model={dashboard.model.data}
              focusDate={dashboard.focusDate}
              onFocus={dashboard.setFocusDate}
            />
          </div>
        </section>

        <section id="context" className="band band-ash" aria-label={t("contextEyebrow")}>
          <PredictionContextChart
            t={t}
            fmt={fmt}
            focusDate={dashboard.focusDate}
            context={dashboard.context}
            focusPrediction={dashboard.focusPrediction}
            isLatest={dashboard.isLatestFocus}
          />
        </section>

        <section id="analysis" className="band band-white" aria-label={t("analysisEyebrow")}>
          <PowerBiReport t={t} embedUrl={POWERBI_URL} />
        </section>
      </main>

      <footer className="site-footer container">
        <p className="footer-title">{t("sourcesTitle")}</p>
        <ul className="footer-sources">
          {DATA_SOURCES.map((source) => (
            <li key={source.label}>
              <a className="link" href={source.href} target="_blank" rel="noreferrer">
                {t(source.label)}
              </a>
            </li>
          ))}
        </ul>
      </footer>
    </div>
  );
}
