import { useState } from "react";
import type { Translate, TranslationKey } from "../i18n/translations";
import { Skeleton } from "./Skeleton";

type PowerBiReportProps = {
  t: Translate;
  /** Already validated https powerbi.com URL, or null when the report is not configured. */
  embedUrl: string | null;
};

const PAGES: Array<{ title: TranslationKey; description: TranslationKey }> = [
  { title: "pbiPage1Title", description: "pbiPage1Desc" },
  { title: "pbiPage2Title", description: "pbiPage2Desc" },
  { title: "pbiPage3Title", description: "pbiPage3Desc" },
  { title: "pbiPage4Title", description: "pbiPage4Desc" },
  { title: "pbiPage5Title", description: "pbiPage5Desc" },
];

export function PowerBiReport({ t, embedUrl }: PowerBiReportProps) {
  const [loaded, setLoaded] = useState(false);

  return (
    <div className="container">
      <div className="section-head">
        <div>
          <span className="eyebrow">{t("analysisEyebrow")}</span>
          <h2>{t("analysisTitle")}</h2>
          <p className="lede">{t("analysisLead")}</p>
        </div>
      </div>

      <div className="card card-data pbi-card" aria-busy={embedUrl !== null && !loaded}>
        {embedUrl ? (
          <div className="pbi-frame">
            {!loaded && <Skeleton variant="block" className="pbi-skeleton" />}
            <iframe
              title={t("pbiFrameTitle")}
              src={embedUrl}
              loading="lazy"
              allowFullScreen
              onLoad={() => setLoaded(true)}
              className={loaded ? "is-loaded" : ""}
            />
          </div>
        ) : (
          <div className="pbi-fallback">
            <h3>{t("pbiPagesLabel")}</h3>
            <ol className="pbi-pages">
              {PAGES.map((page) => (
                <li key={page.title}>
                  <strong>{t(page.title)}</strong>
                  <span>{t(page.description)}</span>
                </li>
              ))}
            </ol>
            <p className="tag tag-ember">{t("pbiPending")}</p>
          </div>
        )}
      </div>

      {embedUrl && (
        <p className="caption">
          <a className="link" href={embedUrl} target="_blank" rel="noreferrer">
            {t("pbiOpen")}
          </a>
        </p>
      )}
    </div>
  );
}
