import type { Language, Translate } from "../i18n/translations";

export const DATE_RANGE = { min: "2000-01-02", max: "2023-12-31", discontinuity: "2015-12-31" } as const;

const DAY_MS = 24 * 60 * 60 * 1000;

export function localeFor(lang: Language): string {
  return lang === "es" ? "es-CO" : "en-GB";
}

export function parseIsoDate(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function addDays(value: string, days: number): string {
  const date = parseIsoDate(value);
  if (!date) return value;
  return toIsoDate(new Date(date.getTime() + days * DAY_MS));
}

export function isWithinDataRange(value: string): boolean {
  return parseIsoDate(value) !== null && value >= DATE_RANGE.min && value <= DATE_RANGE.max;
}

export function getDateValidationMessage(value: string, t: Translate): string {
  if (!value) return "";
  if (!parseIsoDate(value)) return t("invalidDate");
  if (value < DATE_RANGE.min) return t("dateBeforeStart");
  if (value > DATE_RANGE.max) return t("dateAfterEnd");
  if (addDays(value, -1) === DATE_RANGE.discontinuity) return t("referenceMissing");
  return "";
}

export function getAbsoluteError(actual: number | null, predicted: number): number | null {
  return actual === null ? null : Math.abs(predicted - actual);
}

export function getRelativeError(actual: number | null, predicted: number): number | null {
  if (actual === null || actual === 0) return null;
  return (Math.abs(predicted - actual) / Math.abs(actual)) * 100;
}

export function getMatchWithActual(actual: number | null, predicted: number): number | null {
  const relativeError = getRelativeError(actual, predicted);
  return relativeError === null ? null : 100 - relativeError;
}

export type Formatters = {
  date: (value: string) => string;
  shortDate: (value: string) => string;
  kwh: (value: number | null) => string;
  gwh: (kwh: number | null, digits?: number) => string;
  percent: (value: number | null, digits?: number, signed?: boolean) => string;
  axisNumber: (value: number, maxFractionDigits: number) => string;
};

export function createFormatters(lang: Language, t: Translate): Formatters {
  const locale = localeFor(lang);
  const dateFormat = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
  const shortDateFormat = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short", timeZone: "UTC" });
  const kwhFormat = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });

  const withDate = (format: Intl.DateTimeFormat) => (value: string) => {
    const date = parseIsoDate(value);
    return date ? format.format(date) : value;
  };
  const number = (value: number, digits: number, signed = false) =>
    new Intl.NumberFormat(locale, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
      signDisplay: signed ? "exceptZero" : "auto",
    }).format(value);

  return {
    date: withDate(dateFormat),
    shortDate: withDate(shortDateFormat),
    kwh: (value) => (value === null ? t("notAvailable") : `${kwhFormat.format(value)} kWh`),
    gwh: (kwh, digits = 1) => (kwh === null ? t("notAvailable") : `${number(kwh / 1e6, digits)} GWh`),
    percent: (value, digits = 2, signed = false) =>
      value === null || Number.isNaN(value) ? t("notAvailable") : `${number(value, digits, signed)} %`,
    axisNumber: (value, maxFractionDigits) =>
      new Intl.NumberFormat(locale, { maximumFractionDigits: maxFractionDigits }).format(value),
  };
}
