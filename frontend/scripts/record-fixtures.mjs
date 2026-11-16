// Records test fixtures from a running VOLTERRA API on a disposable database seeded with
// synthetic-v1 plus the generated real-style bundles and model run (generated values, never
// real data):
//
//   cd backend && uv run python -m tests.support.fixture_bundles import <volterra_test_db> <data-dir>
//   then serve the API on that database with VOLTERRA_DATA_DIR=<data-dir>
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

/** Error envelopes (422 etc.) are recorded too: the UI must explain them. */
async function getError(path) {
  const response = await fetch(base + path);
  if (response.ok)
    throw new Error(
      `${path}: expected an error, got ${String(response.status)}`,
    );
  return { status: response.status, body: await response.json() };
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

// Real-style batteries (generated bundles): limitation states, null measurements and samples.
// Database ids are random per import, so every battery id is replaced by a fixed one.
const fixedIds = { [battery.id]: "5b0f37f1-3383-4495-a70d-bd0ff24be316" };
const realId = (slug, fixed) => {
  const b = batteries.items.find((x) => x.dataset === slug);
  if (!b)
    throw new Error(
      `No ${slug} battery: import the generated bundles first (see top).`,
    );
  fixedIds[b.id] = fixed;
  return encodeURIComponent(b.id);
};
const calce = realId("calce-test", "00000000-0000-4000-8000-000000000101");
const nasa = realId("nasa-test", "00000000-0000-4000-8000-000000000102");
Object.assign(fixtures, {
  "cycles-calce": await get(`/api/v1/batteries/${calce}/cycles`),
  "cycles-nasa": await get(`/api/v1/batteries/${nasa}/cycles`),
  "samples-nasa-0": await get(
    `/api/v1/batteries/${nasa}/cycles/0/samples?max_points=1500`,
  ),
  "samples-calce-7": await get(
    `/api/v1/batteries/${calce}/cycles/7/samples?max_points=1500`,
  ),
  "error-missing-measurement": await getError(
    `/api/v1/batteries/${calce}/summary`,
  ),
  "error-insufficient-data": await getError(
    `/api/v1/batteries/${nasa}/summary`,
  ),
  "error-no-samples": await getError(
    `/api/v1/batteries/${id}/cycles/0/samples`,
  ),
});

// Phase 7 models: the generated model run (made-up values, tests/support/model_runs.py) that
// fixture_bundles imports next to the bundles.
Object.assign(fixtures, {
  models: await get("/api/v1/models"),
  // Phase 8: the committed simulator evidence (aggregates from offline runs).
  "simulator-evidence": await get("/api/v1/simulator/evidence"),
  "rul-calce": await get(`/api/v1/batteries/${calce}/rul-predictions`),
  "rul-nasa": await get(`/api/v1/batteries/${nasa}/rul-predictions`),
  "error-no-predictions": await getError(
    `/api/v1/batteries/${id}/rul-predictions`,
  ),
});

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
  let text = JSON.stringify(body, null, 2) + "\n";
  for (const [random, fixed] of Object.entries(fixedIds))
    text = text.replaceAll(random, fixed);
  await writeFile(new URL(`${name}.json`, outDir), text);
  console.log(`recorded ${name}.json`);
}
