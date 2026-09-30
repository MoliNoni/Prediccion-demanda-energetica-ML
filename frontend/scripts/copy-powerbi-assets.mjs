import { copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "..", "docs", "powerbi");
const target = join(here, "..", "public", "powerbi", "downloads");
const files = ["reporte_demanda_energetica.pdf", "reporte_demanda_energetica.pbix"];

// The UI always links both downloads, so a missing file must fail the build instead of shipping dead links.
const missing = files.filter((file) => !existsSync(join(source, file)));
if (missing.length > 0) {
  console.error(`[copy-powerbi-assets] missing in ${source}: ${missing.join(", ")}`);
  process.exit(1);
}

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
for (const file of files) {
  copyFileSync(join(source, file), join(target, file));
}
