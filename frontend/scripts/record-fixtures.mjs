// Records test fixtures from a running VOLTERRA API (seeded with synthetic-v1):
//
//   node scripts/record-fixtures.mjs [apiBase]      (default http://127.0.0.1:8000)
//
// The fixtures are real API responses, used only by the unit/component tests (MSW). The app
// itself never uses them. Volatile fields (database latency) are normalised so re-recording an
// unchanged API produces no diff.
import { mkdir, writeFile } from "node:fs/promises";

const base = process.argv[2] ?? "http://127.0.0.1:8000";
const outDir = new URL("../src/test/fixtures/", import.meta.url);

async function get(path) {
  const response = await fetch(base + path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

const health = await get("/api/v1/health");
if (health.database.latency_ms !== null) health.database.latency_ms = 1;

const batteries = await get("/api/v1/batteries");
const battery = batteries.items[0];
if (!battery)
  throw new Error(
    "No battery in the database; seed it first (python -m app.db.seed).",
  );
const id = encodeURIComponent(battery.id);

const fixtures = {
  health,
  batteries,
  anomalies: await get(`/api/v1/batteries/${id}/anomalies`),
  simulator: await get(`/api/v1/batteries/${id}/simulator`),
  cycles: await get(`/api/v1/batteries/${id}/cycles`),
  summary: await get(`/api/v1/batteries/${id}/summary?eol_pct=80`),
  // A second threshold, for the tests that move EOL away from its default (D1, U1).
  "summary-eol-70": await get(`/api/v1/batteries/${id}/summary?eol_pct=70`),
  forecast: await get(`/api/v1/batteries/${id}/forecast?eol_pct=80`),
  "forecast-eol-70": await get(`/api/v1/batteries/${id}/forecast?eol_pct=70`),
  backtest: await get(`/api/v1/batteries/${id}/backtest`),
  insights: await get(`/api/v1/batteries/${id}/insights`),
  // Digital Twin: first, middle, the temperature excursion (warm band) and latest cycle.
  "twin-0": await get(`/api/v1/batteries/${id}/twin?cycle=0`),
  "twin-160": await get(`/api/v1/batteries/${id}/twin?cycle=160`),
  "twin-170": await get(`/api/v1/batteries/${id}/twin?cycle=170`),
  "twin-319": await get(`/api/v1/batteries/${id}/twin?cycle=319`),
};

await mkdir(outDir, { recursive: true });
for (const [name, body] of Object.entries(fixtures)) {
  await writeFile(
    new URL(`${name}.json`, outDir),
    JSON.stringify(body, null, 2) + "\n",
  );
  console.log(`recorded ${name}.json`);
}
