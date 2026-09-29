import type { Health } from "../hooks/useDashboard";
import type { Language, Translate } from "../i18n/translations";

type HeaderProps = {
  t: Translate;
  lang: Language;
  health: Health;
  onLanguageChange: (lang: Language) => void;
};

export function Header({ t, lang, health, onLanguageChange }: HeaderProps) {
  const statusText = health === "checking" ? t("statusChecking") : health === "online" ? t("statusOnline") : t("statusOffline");
  return (
    <header className="site-header container">
      <a className="brand" href="#top">
        {t("brand")}
      </a>
      <nav className="pill" aria-label={t("navLabel")}>
        <a href="#forecast">{t("navForecast")}</a>
        <a href="#context">{t("navContext")}</a>
        <a href="#analysis">{t("navAnalysis")}</a>
        <span className={`status status-${health}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          {statusText}
        </span>
      </nav>
      <div className="lang-toggle" role="group" aria-label={t("languageLabel")}>
        {(["es", "en"] as const).map((code) => (
          <button
            key={code}
            type="button"
            lang={code}
            className={lang === code ? "is-active" : ""}
            aria-pressed={lang === code}
            onClick={() => onLanguageChange(code)}
          >
            {code.toUpperCase()}
          </button>
        ))}
      </div>
    </header>
  );
}
