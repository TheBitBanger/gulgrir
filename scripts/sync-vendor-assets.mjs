import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "..");

const copies = [
  {
    from: path.join(rootDir, "node_modules", "htmx.org", "dist", "htmx.min.js"),
    to: path.join(
      rootDir,
      "src",
      "tracker",
      "static",
      "tracker",
      "vendor",
      "htmx.min.js",
    ),
  },
  {
    from: path.join(rootDir, "node_modules", "flatpickr", "dist", "flatpickr.min.js"),
    to: path.join(
      rootDir,
      "src",
      "tracker",
      "static",
      "tracker",
      "vendor",
      "flatpickr.min.js",
    ),
  },
  {
    from: path.join(rootDir, "node_modules", "flatpickr", "dist", "flatpickr.min.css"),
    to: path.join(
      rootDir,
      "src",
      "tracker",
      "static",
      "tracker",
      "vendor",
      "flatpickr.min.css",
    ),
  },
];

for (const copy of copies) {
  await mkdir(path.dirname(copy.to), { recursive: true });
  await copyFile(copy.from, copy.to);
}
