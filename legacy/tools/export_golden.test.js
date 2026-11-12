/*
 * Tests for the golden fixture exporter (Phase 1). Uses only Node's built-in test runner.
 *   node --test legacy/tools/export_golden.test.js
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");

const {
  generate,
  check,
  toJson,
  DEFAULT_OUT_DIR,
  LEGACY_SOURCES,
} = require("./export_golden.js");

const EXPORTER = path.join(__dirname, "export_golden.js");
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const sha256 = (buf) => crypto.createHash("sha256").update(buf).digest("hex");
const readFixture = (name) =>
  JSON.parse(fs.readFileSync(path.join(DEFAULT_OUT_DIR, name), "utf8"));
const fixtureFiles = () =>
  fs
    .readdirSync(DEFAULT_OUT_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort();

function runExporterInto(dir) {
  const r = spawnSync(process.execPath, [EXPORTER, "--out", dir], {
    encoding: "utf8",
  });
  assert.equal(r.status, 0, `exporter failed: ${r.stderr}`);
}

test("two separate exporter processes produce byte-identical fixtures", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "volterra-golden-"));
  try {
    const a = path.join(tmp, "a");
    const b = path.join(tmp, "b");
    runExporterInto(a);
    runExporterInto(b);
    const filesA = fs.readdirSync(a).sort();
    assert.deepEqual(filesA, fs.readdirSync(b).sort());
    assert.ok(filesA.length >= 11);
    for (const f of filesA) {
      assert.ok(
        fs
          .readFileSync(path.join(a, f))
          .equals(fs.readFileSync(path.join(b, f))),
        `${f} differs`,
      );
    }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("committed fixtures match a fresh export (check() reports no problems)", () => {
  assert.deepEqual(check(), []);
});

test("CLI --check exits 0", () => {
  const r = spawnSync(process.execPath, [EXPORTER, "--check"], {
    encoding: "utf8",
  });
  assert.equal(r.status, 0, r.stderr);
});

test("manifest pins the unchanged legacy sources and every fixture file", () => {
  const manifest = readFixture("manifest.json");
  for (const f of LEGACY_SOURCES) {
    const key = `legacy/${f}`;
    assert.equal(
      manifest.legacy_sources_sha256[key],
      sha256(fs.readFileSync(path.join(REPO_ROOT, key))),
      key,
    );
  }
  const listed = Object.keys(manifest.fixtures_sha256).sort();
  assert.deepEqual(
    listed,
    fixtureFiles().filter((f) => f !== "manifest.json"),
  );
  for (const f of listed) {
    assert.equal(
      manifest.fixtures_sha256[f],
      sha256(fs.readFileSync(path.join(DEFAULT_OUT_DIR, f))),
      f,
    );
  }
});

test("every fixture declares meta: name, schema version, description, provenance and units", () => {
  for (const f of fixtureFiles()) {
    const { meta } = readFixture(f);
    assert.ok(meta, `${f} has meta`);
    assert.equal(meta.fixture, f.replace(/\.json$/, ""));
    assert.equal(meta.schema_version, 1);
    assert.equal(typeof meta.description, "string");
    if (f === "manifest.json") continue;
    assert.ok(
      ["measured", "simulated", "fitted", "predicted", "assumed"].includes(
        meta.provenance,
      ),
      `${f} provenance`,
    );
    assert.equal(typeof meta.units, "object", `${f} units`);
    assert.ok(
      Array.isArray(meta.source) &&
        meta.source.every((s) => s.startsWith("legacy/")),
      `${f} source`,
    );
  }
});

test("fixtures are standard JSON with LF line endings and a trailing newline", () => {
  for (const f of fixtureFiles()) {
    const text = fs.readFileSync(path.join(DEFAULT_OUT_DIR, f), "utf8");
    assert.ok(!text.includes("\r"), `${f} has CR characters`);
    assert.ok(text.endsWith("}\n"), `${f} trailing newline`);
    assert.doesNotThrow(() => JSON.parse(text), f);
  }
});

test("in-process generation is repeatable and isolated between runs", () => {
  assert.deepEqual(generate(), generate());
});

test("serializer encodes non-finite numbers and rejects undefined", () => {
  assert.equal(
    toJson([NaN, Infinity, -Infinity, 1.5]),
    '["NaN", "Infinity", "-Infinity", 1.5]',
  );
  assert.throws(() => toJson({ a: undefined }), /undefined/);
});

/* Independent anchors: prototype outputs documented in ARCHITECTURE_PLAN.md §3.2-3.6. */
test("anchor values match the prototype outputs recorded in the architecture plan", () => {
  const dataset = readFixture("dataset.json");
  assert.equal(dataset.rows.length, 320);
  assert.equal(dataset.parameters.nominal_capacity_ah, 2);

  const soh = readFixture("soh_rul.json");
  assert.equal(soh.current.soh_now_pct.toFixed(2), "86.09");
  assert.equal(soh.current.fade_pct_per_cycle.toFixed(4), "0.0540");
  assert.equal(Math.round(soh.current.rul_cycles_at_default_eol), 113);
  const i80 = soh.rul_by_eol.find((r) => r.eol_pct === 80).interval_95;
  assert.deepEqual([Math.round(i80.lower), Math.round(i80.upper)], [111, 114]);

  assert.equal(readFixture("backtest.json").mae.toFixed(2), "0.58");

  const an = readFixture("anomalies.json");
  assert.deepEqual(
    an.events.map((e) => e.cycle),
    [125, 127, 130, 170, 254, 271, 315, 319],
  );
  assert.deepEqual(an.ground_truth_vs_detected.temp.detected, [170]); // F1 captured as-is
  assert.deepEqual(
    an.ground_truth_vs_detected.soh.detected,
    [125, 127, 254, 315, 319],
  ); // F2

  const sim = readFixture("simulator.json");
  assert.equal(sim.consistency_check_F4.simulator_baseline_cycles_to_eol, 106); // F4

  const insights = readFixture("insights.json");
  assert.equal(insights.insights.length, 4);
  assert.match(insights.insights[1], /^Fade is accelerating/); // F5
});
