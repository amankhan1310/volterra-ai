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

async function send(method, path, body) {
  const response = await fetch(base + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(`${method} ${path}: HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
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

// What-If Simulator: the defaults and one changed temperature (the tests move that slider).
const simulator = fixtures.simulator;
const simulate = (params) =>
  send("POST", `/api/v1/batteries/${id}/simulate`, {
    params,
    include_trajectories: true,
  });
fixtures["simulate-default"] = await simulate(simulator.defaults);
fixtures["simulate-t35"] = await simulate({
  ...simulator.defaults,
  temp_c: 35,
});

// Charging Advisor at the defaults and with EOL 70% from 90% SOH (the D1 tests move both).
fixtures["advisor"] = await get(
  `/api/v1/batteries/${id}/advisor?eol_pct=80&start_soh_pct=86.1`,
);
fixtures["advisor-eol70-soh90"] = await get(
  `/api/v1/batteries/${id}/advisor?eol_pct=70&start_soh_pct=90`,
);
// Initial SOH below the threshold: every count is 0 and v1 reports 0% for each change (F8).
fixtures["advisor-eol90-soh85"] = await get(
  `/api/v1/batteries/${id}/advisor?eol_pct=90&start_soh_pct=85`,
);

// One saved scenario, for its exact response shape. It is created and deleted straight away so
// the database is left as it was; ids and timestamps are normalised so re-recording is stable.
const created = await send("POST", `/api/v1/batteries/${id}/scenarios`, {
  name: "Scenario 1",
  params: simulator.defaults,
});
await send("DELETE", `/api/v1/scenarios/${encodeURIComponent(created.id)}`);
fixtures.scenario = {
  ...created,
  id: "00000000-0000-4000-8000-000000000001",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

await mkdir(outDir, { recursive: true });
for (const [name, body] of Object.entries(fixtures)) {
  await writeFile(
    new URL(`${name}.json`, outDir),
    JSON.stringify(body, null, 2) + "\n",
  );
  console.log(`recorded ${name}.json`);
}
