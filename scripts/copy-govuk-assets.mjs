import { copyFile, mkdir } from "node:fs/promises";

await mkdir("app/static/js", { recursive: true });
await copyFile(
  "node_modules/govuk-frontend/dist/govuk/govuk-frontend.min.js",
  "app/static/js/govuk-frontend.min.js",
);
