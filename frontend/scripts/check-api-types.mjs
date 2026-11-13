// Fails if src/api/schema.d.ts is not what `npm run api:types` generates from backend/openapi.json.
// Mirrors the backend's OpenAPI drift check: a contract change must update the frontend types.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const committed = join(root, "src/api/schema.d.ts");
const spec = join(root, "../backend/openapi.json");
// The package's `bin` entry (its export map does not expose the CLI to require.resolve).
const cli = join(root, "node_modules/openapi-typescript/bin/cli.js");

const dir = mkdtempSync(join(tmpdir(), "volterra-api-types-"));
try {
  const fresh = join(dir, "schema.d.ts");
  execFileSync(process.execPath, [cli, spec, "-o", fresh], { stdio: "pipe" });
  const normalise = (text) => text.replace(/\r\n/g, "\n");
  if (
    normalise(readFileSync(fresh, "utf8")) !==
    normalise(readFileSync(committed, "utf8"))
  ) {
    console.error(
      "src/api/schema.d.ts is out of date with backend/openapi.json. Run `npm run api:types` and commit.",
    );
    process.exit(1);
  }
  console.log("src/api/schema.d.ts matches backend/openapi.json");
} finally {
  rmSync(dir, { recursive: true, force: true });
}
