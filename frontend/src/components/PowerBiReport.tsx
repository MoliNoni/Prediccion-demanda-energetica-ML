import { useEffect, useRef, useState } from "react";
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

const PAGE_IMAGE_BASE = "/powerbi/pages/page-";
const DOWNLOAD_BASE = "/powerbi/downloads/reporte_demanda_energetica";

export function PowerBiReport({ t, embedUrl }: PowerBiReportProps) {
  const [loaded, setLoaded] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const activePage = active === null ? null : PAGES[active];

  useEffect(() => {
    const dialog = dialogRef.current;
    if (activePage && dialog && !dialog.open) {
      opener.current = document.activeElement as HTMLElement | null;
      dialog.showModal();
    }
  }, [activePage]);

  useEffect(() => {
    if (active === null) opener.current?.focus();
  }, [active]);

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
            <p className="pbi-note">{t("pbiGalleryNote")}</p>
            <ol className="pbi-gallery" aria-label={t("pbiPagesLabel")}>
              {PAGES.map((page, index) => (
                <li key={page.title}>
                  <button type="button" className="pbi-figure" onClick={() => setActive(index)}>
                    <img
                      src={`${PAGE_IMAGE_BASE}${index + 1}.webp`}
                      alt={`${t("pbiImageAlt")}: ${t(page.title)}`}
                      width={1600}
                      height={918}
                      loading="lazy"
                    />
                    <strong>{t(page.title)}</strong>
                    <span>{t(page.description)}</span>
                  </button>
                </li>
              ))}
            </ol>
            <div className="button-row pbi-downloads">
              <a className="btn btn-primary" href={`${DOWNLOAD_BASE}.pdf`} download>
                {t("pbiDownloadPdf")}
              </a>
              <a className="btn btn-ghost" href={`${DOWNLOAD_BASE}.pbix`} download>
                {t("pbiDownloadPbix")}
              </a>
            </div>
            <dialog
              ref={dialogRef}
              className="pbi-dialog"
              aria-label={activePage ? t(activePage.title) : undefined}
              onClose={() => setActive(null)}
              onClick={(event) => {
                if (event.target === event.currentTarget) event.currentTarget.close();
              }}
            >
              {activePage && (
                <>
                  <button type="button" className="btn btn-ghost pbi-close" onClick={() => dialogRef.current?.close()}>
                    {t("pbiClose")}
                  </button>
                  <img
                    src={`${PAGE_IMAGE_BASE}${(active ?? 0) + 1}.webp`}
                    alt={`${t("pbiImageAlt")}: ${t(activePage.title)}`}
                    width={1600}
                    height={918}
                  />
                  <p>
                    <strong>{t(activePage.title)}</strong> {t(activePage.description)}
                  </p>
                </>
              )}
            </dialog>
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
