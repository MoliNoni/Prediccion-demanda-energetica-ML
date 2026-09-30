import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "..", "docs", "powerbi");
const target = join(here, "..", "public", "powerbi", "downloads");
const files = ["reporte_demanda_energetica.pdf", "reporte_demanda_energetica.pbix"];

mkdirSync(target, { recursive: true });
for (const file of files) {
  const from = join(source, file);
  if (!existsSync(from)) {
    console.warn(`[copy-powerbi-assets] missing ${from}, skipped`);
    continue;
  }
  copyFileSync(from, join(target, file));
}
