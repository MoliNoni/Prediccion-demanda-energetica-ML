/** Only https URLs hosted on powerbi.com are accepted; anything else counts as "not configured". */
export function resolvePowerBiUrl(raw: string | undefined): string | null {
  const value = raw?.trim();
  if (!value) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    const trusted = host === "powerbi.com" || host.endsWith(".powerbi.com");
    return url.protocol === "https:" && trusted ? url.toString() : null;
  } catch {
    return null;
  }
}
