import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { Translate, TranslationKey } from "../i18n/translations";
import { Skeleton } from "./Skeleton";

type PowerBiReportProps = {
  t: Translate;
  /** Already validated https powerbi.com URL, or null when the report is not configured. */
  embedUrl: string | null;
};

type PageVariant = { version: string; image: string };
type PageEntry = { title: TranslationKey; description: TranslationKey; variants?: PageVariant[] };

const PAGES: PageEntry[] = [
  { title: "pbiPage1Title", description: "pbiPage1Desc" },
  { title: "pbiPage2Title", description: "pbiPage2Desc" },
  { title: "pbiPage3Title", description: "pbiPage3Desc" },
  { title: "pbiPage4Title", description: "pbiPage4Desc" },
  {
    title: "pbiPage5Title",
    description: "pbiPage5Desc",
    variants: [
      { version: "1.1.0", image: "page-5-v1.1.0.webp" },
      { version: "1.2.0", image: "page-5-v1.2.0.webp" },
    ],
  },
];

const PAGE_IMAGE_BASE = "/powerbi/pages/page-";
const PAGE_IMAGE_DIR = "/powerbi/pages/";
const DOWNLOAD_BASE = "/powerbi/downloads/reporte_demanda_energetica";

function imageSrc(page: PageEntry, index: number, variant: number): string {
  const chosen = page.variants?.[variant];
  return chosen ? `${PAGE_IMAGE_DIR}${chosen.image}` : `${PAGE_IMAGE_BASE}${index + 1}.webp`;
}

function figureAlt(t: Translate, page: PageEntry, variant: number): string {
  const version = page.variants?.[variant]?.version;
  return `${t("pbiImageAlt")}: ${t(page.title)}${version ? ` (${t("modelVersionLabel", { version })})` : ""}`;
}

/** Image that swaps to a neutral placeholder while its file is missing, and recovers when the source changes. */
function ReportImage({ src, alt, pendingLabel, eager }: { src: string; alt: string; pendingLabel: string; eager?: boolean }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  if (failed) {
    return (
      <div className="pbi-placeholder" role="img" aria-label={`${alt}. ${pendingLabel}`}>
        <span>{pendingLabel}</span>
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      width={1600}
      height={918}
      loading={eager ? undefined : "lazy"}
      onError={() => setFailed(true)}
    />
  );
}

function VariantControls({ t, page, variant, onStep, dialog }: { t: Translate; page: PageEntry; variant: number; onStep: (delta: number) => void; dialog?: boolean }) {
  if (!page.variants) return null;
  return (
    <div className={dialog ? "pbi-variant pbi-variant-dialog" : "pbi-variant"}>
      <button type="button" className="btn btn-ghost pbi-arrow" aria-label={t("pbiSlidePrevious")} onClick={() => onStep(-1)}>
        <span aria-hidden="true">&larr;</span>
      </button>
      <span className="tag pbi-version" aria-live="polite">
        {t("modelVersionLabel", { version: page.variants[variant].version })}
      </span>
      <button type="button" className="btn btn-ghost pbi-arrow" aria-label={t("pbiSlideNext")} onClick={() => onStep(1)}>
        <span aria-hidden="true">&rarr;</span>
      </button>
    </div>
  );
}

export function PowerBiReport({ t, embedUrl }: PowerBiReportProps) {
  const [loaded, setLoaded] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [variants, setVariants] = useState<Record<number, number>>({});
  const activePage = active === null ? null : PAGES[active];

  function stepVariant(index: number, delta: number) {
    const count = PAGES[index].variants?.length ?? 1;
    setVariants((previous) => ({ ...previous, [index]: ((((previous[index] ?? 0) + delta) % count) + count) % count }));
  }

  function onVariantKeyDown(event: KeyboardEvent<HTMLElement>, index: number) {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      stepVariant(index, event.key === "ArrowLeft" ? -1 : 1);
    }
  }

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
                <li key={page.title} className="pbi-item" onKeyDown={page.variants ? (event) => onVariantKeyDown(event, index) : undefined}>
                  <button type="button" className="pbi-figure" onClick={() => setActive(index)}>
                    <ReportImage
                      src={imageSrc(page, index, variants[index] ?? 0)}
                      alt={figureAlt(t, page, variants[index] ?? 0)}
                      pendingLabel={t("pbiImagePending")}
                    />
                    <strong>{t(page.title)}</strong>
                    <span>{t(page.description)}</span>
                  </button>
                  <VariantControls t={t} page={page} variant={variants[index] ?? 0} onStep={(delta) => stepVariant(index, delta)} />
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
                  <div
                    className="pbi-dialog-figure"
                    onKeyDown={activePage.variants ? (event) => onVariantKeyDown(event, active ?? 0) : undefined}
                  >
                    <ReportImage
                      eager
                      src={imageSrc(activePage, active ?? 0, variants[active ?? 0] ?? 0)}
                      alt={figureAlt(t, activePage, variants[active ?? 0] ?? 0)}
                      pendingLabel={t("pbiImagePending")}
                    />
                    <VariantControls
                      t={t}
                      page={activePage}
                      variant={variants[active ?? 0] ?? 0}
                      onStep={(delta) => stepVariant(active ?? 0, delta)}
                      dialog
                    />
                  </div>
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
