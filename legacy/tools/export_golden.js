#!/usr/bin/env node
/*
 * Golden reference fixture exporter for the VOLTERRA AI legacy prototype (Phase 1).
 *
 * Executes the UNMODIFIED legacy/core.js and legacy/ui.js inside a Node `vm` sandbox with a
 * minimal DOM stub (the same load order as legacy/index.html), reads the prototype's own
 * computed values and functions, and writes deterministic JSON fixtures to
 * backend/tests/golden/. These fixtures are the reference the Python port (Phase 2) must match.
 *
 * Known prototype defects (ARCHITECTURE_PLAN.md §3.6, F1–F8) are captured AS-IS on purpose.
 *
 * Usage:
 *   node legacy/tools/export_golden.js              write fixtures to backend/tests/golden/
 *   node legacy/tools/export_golden.js --out DIR    write fixtures to DIR
 *   node legacy/tools/export_golden.js --check      verify: two independent runs are identical
 *                                                   AND match the committed fixtures (exit 1 if not)
 *
 * No dependencies beyond Node.js (>= 18). Output contains no timestamps or machine-specific data.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const crypto = require("crypto");

const EXPORTER_VERSION = "1.0.0";
const SCHEMA_VERSION = 1;
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const LEGACY_DIR = path.join(REPO_ROOT, "legacy");
const LEGACY_SOURCES = ["index.html", "core.js", "ui.js", "style.css"];
const LEGACY_SCRIPTS = ["core.js", "ui.js"]; // load order from legacy/index.html
const DEFAULT_OUT_DIR = path.join(REPO_ROOT, "backend", "tests", "golden");

/* ------------------------------------------------------------------------------------------ */
/* Sandbox: run the legacy scripts exactly as the browser would, against a DOM stub.          */
/* ------------------------------------------------------------------------------------------ */

function makeElement() {
  return {
    innerHTML: "",
    textContent: "",
    value: "",
    scrollTop: 0,
    style: {},
    dataset: {},
    classList: {
      add() {},
      remove() {},
      toggle() {
        return false;
      },
      contains() {
        return false;
      },
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    setAttribute() {},
    removeAttribute() {},
    toggleAttribute() {
      return false;
    },
    appendChild() {},
    addEventListener() {},
  };
}

function createSandbox() {
  const elements = new Map();
  const getElementById = (id) => {
    if (!elements.has(id)) elements.set(id, makeElement());
    return elements.get(id);
  };
  const sandbox = {
    document: {
      getElementById,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => makeElement(),
      body: makeElement(),
    },
    location: { hash: "" },
    // Timers/animation are no-ops: they only drive visual transitions and toasts.
    requestAnimationFrame: () => 0,
    setTimeout: () => 0,
    clearTimeout: () => {},
    addEventListener: () => {},
    alert: () => {},
    prompt: () => null,
  };
  const ctx = vm.createContext(sandbox);
  // `window.echarts` is left undefined, so the prototype takes its SVG-fallback code path.
  vm.runInContext("globalThis.window = globalThis;", ctx);
  return ctx;
}

/** Load the legacy scripts into a fresh sandbox and expose their top-level bindings. */
function loadLegacy() {
  const ctx = createSandbox();
  for (const file of LEGACY_SCRIPTS) {
    const code = fs.readFileSync(path.join(LEGACY_DIR, file), "utf8");
    vm.runInContext(code, ctx, { filename: `legacy/${file}` });
  }
  // Top-level const/let bindings live in the context's global lexical scope, so a later
  // script in the same context can read them without any change to the legacy sources.
  return vm.runInContext(
    `({ BRAND, N, NOM, W0, D, F, BT, AN, BASE, P: { ...P }, sohNow, fade, SL, SC2, SCol,
        rng, lin, med, col, rulAt, rate, sohAt, eolN, insights, hcol, cond, xt })`,
    ctx,
    { filename: "export_golden:extract" },
  );
}

/* ------------------------------------------------------------------------------------------ */
/* Helpers                                                                                     */
/* ------------------------------------------------------------------------------------------ */

function assert(cond, msg) {
  if (!cond) throw new Error(`export_golden sanity check failed: ${msg}`);
}

const sha256 = (buf) => crypto.createHash("sha256").update(buf).digest("hex");
const range = (a, b) => Array.from({ length: b - a + 1 }, (_, k) => a + k); // inclusive
const fitRecord = (f) => ({
  slope: f.s,
  intercept: f.b,
  residual_sd: f.sd,
  slope_se: f.se,
});

function meta(fixture, description, extra) {
  return { fixture, schema_version: SCHEMA_VERSION, description, ...extra };
}

/**
 * Deterministic JSON writer.
 * - 2-space indentation, keys in insertion order, LF line endings, trailing newline.
 * - Arrays of scalars are written inline (wrapped every 10 values) to keep diffs readable.
 * - Non-finite numbers, which plain JSON cannot represent, are written as the strings
 *   "NaN", "Infinity" and "-Infinity" (documented in backend/tests/golden/README.md).
 * - `undefined` is rejected so that a missing value can never silently disappear.
 */
function toJson(value, indent = "") {
  const scalar = (v) =>
    v === null || ["number", "string", "boolean"].includes(typeof v);
  if (value === undefined) throw new Error("undefined value in fixture");
  if (value === null) return "null";
  if (typeof value === "number") {
    if (Number.isFinite(value)) return JSON.stringify(value);
    return JSON.stringify(
      Number.isNaN(value) ? "NaN" : value > 0 ? "Infinity" : "-Infinity",
    );
  }
  if (typeof value === "string" || typeof value === "boolean")
    return JSON.stringify(value);
  const inner = indent + "  ";
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    if (value.every(scalar)) {
      const items = value.map((v) => toJson(v));
      if (items.length <= 10) return `[${items.join(", ")}]`;
      const lines = [];
      for (let k = 0; k < items.length; k += 10)
        lines.push(inner + items.slice(k, k + 10).join(", "));
      return `[\n${lines.join(",\n")}\n${indent}]`;
    }
    return `[\n${value.map((v) => inner + toJson(v, inner)).join(",\n")}\n${indent}]`;
  }
  const keys = Object.keys(value);
  if (keys.length === 0) return "{}";
  const body = keys.map(
    (k) => `${inner}${JSON.stringify(k)}: ${toJson(value[k], inner)}`,
  );
  return `{\n${body.join(",\n")}\n${indent}}`;
}

/* ------------------------------------------------------------------------------------------ */
/* Fixture builders                                                                            */
/* ------------------------------------------------------------------------------------------ */

const KNOWN_ISSUES = {
  F1: "Temperature detector misses injected spikes: global median/MAD is inflated by the sinusoidal baseline.",
  F2: "Capacity-step detector raises false positives (no capacity steps are injected); edge cycles affected by truncated centred window.",
  F3: "RUL '95% fit interval' uses slope standard error only, so it is far narrower than real forecast error.",
  F4: "Simulator baseline cycles-to-EOL differs from the Overview linear RUL for identical conditions.",
  F5: "Insight #2 always says 'Fade is accelerating' regardless of the computed slopes.",
  F6: "Linear model is structurally biased on quadratic-fade data.",
  F7: "Capacity-step detector uses a centred window, i.e. future cycles (not causal).",
  F8: "Advisor delta for a null/zero cycles-to-EOL is 0 in ui.js but null in core.js.",
};

function buildDataset(L) {
  return {
    meta: meta(
      "dataset",
      "Seeded synthetic battery dataset generated by the prototype.",
      {
        provenance: "simulated",
        source: ["legacy/core.js:6-32"],
        units: {
          cycle: "cycle index (0-based)",
          capacity_ah: "Ah",
          soh_pct: "% of nominal capacity",
          temp_c: "°C",
          voltage_v: "V",
        },
      },
    ),
    parameters: {
      prng: "mulberry32",
      seed: 7,
      n_cycles: L.N,
      nominal_capacity_ah: L.NOM,
      noise:
        "gn() = (R() + R() + R() - 1.5) * 1.15, with R = mulberry32(7) shared by all draws",
      draw_order:
        "for each cycle i ascending: capacity gn() (3 draws), then temp gn() (3), then voltage gn() (3)",
      formulas: {
        capacity_ah: "NOM * (1 - 0.00028*i - 0.0000005*i^2) + gn() * 0.004",
        soh_pct: "capacity_ah / NOM * 100",
        temp_c: "24 + 3*sin(i/22) + gn()*0.6 + (i in [90,170,251] ? 9 : 0)",
        voltage_v: "3.72 - 0.0002*i + gn()*0.01 - (i in [130,271] ? 0.18 : 0)",
      },
      injected_anomalies: {
        temp_spike: { cycles: [90, 170, 251], delta_c: 9 },
        voltage_dip: { cycles: [130, 271], delta_v: -0.18 },
        capacity_step: { cycles: [], note: "none injected" },
      },
    },
    columns: ["cycle", "capacity_ah", "soh_pct", "temp_c", "voltage_v"],
    rows: L.D.map((d) => [d.i, d.cap, d.soh, d.temp, d.volt]),
  };
}

function buildPrng(L) {
  const draws = (seed, n) => {
    const r = L.rng(seed);
    return Array.from({ length: n }, () => r());
  };
  const seeds = [7, 0, 1, 42, -1, 2147483648, 4294967296];
  return {
    meta: meta(
      "prng",
      "Raw mulberry32 outputs from the prototype's rng(seed).",
      {
        provenance: "simulated",
        source: ["legacy/core.js:6-14"],
        units: {
          value: "dimensionless, in [0, 1)",
          uint32: "value * 2^32 (exact integer)",
        },
        notes: [
          "Each value equals uint32 / 2^32 exactly, so a correct port matches bit-for-bit.",
          "Seeds are coerced with `a |= 0` (int32), so 2147483648 -> -2147483648 and 4294967296 -> 0.",
        ],
      },
    ),
    sequences: seeds.map((seed) => {
      const values = draws(seed, seed === 7 ? 64 : 8);
      return { seed, values, uint32: values.map((v) => v * 4294967296) };
    }),
  };
}

function buildRegression(L) {
  const fitOver = (from, to, xKey, yKey) => {
    const rows = L.D.slice(from, to + 1);
    return L.lin(
      rows.map((d) => d[xKey]),
      rows.map((d) => d[yKey]),
    );
  };
  const recent = fitOver(L.W0, L.N - 1, "i", "soh");
  for (const k of ["s", "b", "sd", "se"])
    assert(recent[k] === L.F[k], `recent fit ${k} matches F`);

  const linCase = (name, xs, ys, note) => ({
    name,
    x: xs,
    y: ys,
    expected: fitRecord(L.lin(xs, ys)),
    ...(note ? { note } : {}),
  });
  const medCase = (name, values, note) => ({
    name,
    values,
    expected: L.med(values),
    ...(note ? { note } : {}),
  });

  return {
    meta: meta(
      "regression",
      "Ordinary least squares `lin` and median `med` as implemented in the prototype.",
      {
        provenance: "fitted",
        source: [
          "legacy/core.js:35-56",
          "legacy/core.js:57-61",
          "legacy/core.js:66-73",
          "legacy/core.js:277-291",
          "legacy/ui.js:196-199",
        ],
        units: {
          slope: "y-units per x-unit",
          intercept: "y-units",
          residual_sd: "y-units",
          slope_se: "y-units per x-unit",
        },
        definitions: {
          slope: "Sxy / Sxx",
          intercept: "mean(y) - slope * mean(x)",
          residual_sd: "sqrt(sum((y - intercept - slope*x)^2) / (n - 2))",
          slope_se: "residual_sd / sqrt(Sxx)",
        },
      },
    ),
    fits: [
      {
        name: "recent_trend",
        purpose:
          "SOH trend used for SOH-now, fade rate and RUL (the prototype's F)",
        x: "cycle",
        y: "soh_pct",
        cycles: { from: L.W0, to_inclusive: L.N - 1 },
        n: L.N - L.W0,
        ...fitRecord(recent),
      },
      {
        name: "backtest_train",
        purpose: "Backtest fit (see backtest.json)",
        x: "cycle",
        y: "soh_pct",
        cycles: { from: 100, to_inclusive: 219 },
        n: 120,
        ...fitRecord(fitOver(100, 219, "i", "soh")),
      },
      {
        name: "first_half",
        purpose:
          "Early fade rate used by insights and the Overview acceleration check",
        x: "cycle",
        y: "soh_pct",
        cycles: { from: 0, to_inclusive: 159 },
        n: 160,
        ...fitRecord(fitOver(0, 159, "i", "soh")),
      },
      {
        name: "temp_vs_soh",
        purpose:
          "Computed in insights() but never used (dead code); captured for completeness",
        x: "temp_c",
        y: "soh_pct",
        cycles: { from: 0, to_inclusive: L.N - 1 },
        n: L.N,
        ...fitRecord(fitOver(0, L.N - 1, "temp", "soh")),
      },
    ],
    lin_test_vectors: [
      linCase(
        "perfect_line",
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 3, 5, 7, 9, 11, 13, 15, 17, 19],
      ),
      linCase(
        "negative_slope_noisy",
        [0, 1, 2, 3, 4, 5],
        [100, 99.1, 97.8, 97.2, 95.9, 95.1],
      ),
      linCase("unsorted_x", [5, 1, 4, 2, 3], [2.5, 0.4, 2.1, 1.2, 1.4]),
      linCase(
        "two_points",
        [0, 1],
        [1, 2],
        "n - 2 = 0, so residual_sd and slope_se are NaN",
      ),
      linCase(
        "constant_x",
        [3, 3, 3, 3],
        [1, 2, 3, 4],
        "Sxx = 0, so slope is NaN",
      ),
    ],
    med_test_vectors: [
      medCase("odd", [3, 1, 2]),
      medCase("even", [4, 1, 3, 2]),
      medCase("duplicates", [2, 2, 2, 5, 5]),
      medCase("negatives", [-3.5, 1.25, -0.5, 7]),
      medCase("single", [42]),
      medCase("empty", [], "returns NaN"),
    ],
  };
}

function buildSohRul(L) {
  const { F, P } = L;
  const interval = (E) => ({
    lower: L.rulAt(E, F.s - 1.96 * F.se),
    upper: L.rulAt(E, F.s + 1.96 * F.se),
  });
  const ex = L.xt();
  const forecast = range(L.N - 1, ex - 1).map((i) => F.b + F.s * i);
  return {
    meta: meta(
      "soh_rul",
      "Current SOH, fade rate and linear RUL with the prototype's 95% fit interval.",
      {
        provenance: "predicted",
        source: [
          "legacy/core.js:57-64",
          "legacy/core.js:181-186",
          "legacy/ui.js:190",
          "legacy/ui.js:193-195",
          "legacy/ui.js:240-252",
        ],
        units: {
          soh_now_pct: "%",
          fade_pct_per_cycle: "% SOH per cycle",
          rul_cycles: "cycles",
          eol_pct: "% SOH",
          forecast: "% SOH per cycle index",
        },
        definitions: {
          soh_now_pct:
            "intercept + slope * (N - 1) of the recent_trend fit (fitted, not observed)",
          fade_pct_per_cycle: "-slope of the recent_trend fit",
          rul_cycles: "slope < 0 ? max(0, (soh_now - eol) / -slope) : null",
          interval_95:
            "rul_cycles recomputed with slope -/+ 1.96 * slope_se (lower uses the steeper slope)",
        },
        known_issues: { F3: KNOWN_ISSUES.F3, F6: KNOWN_ISSUES.F6 },
      },
    ),
    current: {
      soh_now_pct: L.sohNow,
      soh_now_provenance: "fitted",
      observed_last_soh_pct: L.D[L.N - 1].soh,
      fade_pct_per_cycle: L.fade,
      fit_cycles: { from: L.W0, to_inclusive: L.N - 1 },
      default_eol_pct: P.E,
      rul_cycles_at_default_eol: L.rulAt(P.E),
    },
    rul_by_eol: range(60, 90).map((E) => ({
      eol_pct: E,
      rul_cycles: L.rulAt(E),
      interval_95: interval(E),
    })),
    rul_with_explicit_slope: [
      {
        eol_pct: 80,
        slope: 0,
        rul_cycles: L.rulAt(80, 0),
        note: "non-negative slope returns null",
      },
      { eol_pct: 80, slope: 0.01, rul_cycles: L.rulAt(80, 0.01) },
      { eol_pct: 80, slope: -0.1, rul_cycles: L.rulAt(80, -0.1) },
    ],
    forecast: {
      description:
        "Linear forecast drawn on the Overview timeline (ui.js xt() sets the extent).",
      extent_cycles: ex,
      extent_formula:
        "min(N + ceil((rul_at_default_eol || 200) * 1.4), N + 500)",
      from_cycle: L.N - 1,
      to_cycle_inclusive: ex - 1,
      values: forecast,
    },
    gauge: {
      description:
        "Inner ring of the Overview gauge: fraction of life used down to the EOL threshold.",
      life_used_fraction: Math.min(1, (100 - L.sohNow) / (100 - P.E)),
      formula:
        "min(1, (100 - soh_now) / (100 - eol))  [transcribed from legacy/ui.js:242]",
    },
  };
}

function buildBacktest(L) {
  const f = L.lin(
    L.D.slice(100, 220).map((d) => d.i),
    L.D.slice(100, 220).map((d) => d.soh),
  );
  const perCycle = L.D.slice(220).map((d) => {
    const predicted = f.b + f.s * d.i;
    return [d.i, d.soh, predicted, Math.abs(predicted - d.soh)];
  });
  const mae =
    perCycle.map((r) => r[3]).reduce((a, b) => a + b) / perCycle.length;
  assert(mae === L.BT.mae, "recomputed backtest MAE equals legacy BT.mae");
  return {
    meta: meta(
      "backtest",
      "Time-ordered hold-out backtest of the straight-line SOH forecast.",
      {
        provenance: "fitted",
        source: ["legacy/core.js:65-73"],
        units: {
          soh_pct: "%",
          abs_error: "SOH percentage points",
          mae: "SOH percentage points",
        },
      },
    ),
    train_cycles: { from: 100, to_inclusive: 219 },
    test_cycles: { from: 220, to_inclusive: L.N - 1 },
    fit: fitRecord(f),
    columns: ["cycle", "observed_soh_pct", "predicted_soh_pct", "abs_error"],
    per_cycle: perCycle,
    mae: L.BT.mae,
  };
}

function buildAnomalies(L) {
  const soh = L.col("soh");
  const residual = soh.map(
    (v, i) => v - L.med(soh.slice(Math.max(0, i - 7), i + 8)),
  );
  const channels = [
    {
      key: "temp",
      label: "Temperature excursion",
      unit: "°C",
      input: "dataset temp_c",
      values: L.col("temp"),
    },
    {
      key: "volt",
      label: "Voltage dip/spike",
      unit: "V",
      input: "dataset voltage_v",
      values: L.col("volt"),
    },
    {
      key: "soh",
      label: "Irregular capacity step",
      unit: "% resid.",
      input:
        "soh_pct minus median of soh_pct over cycles [max(0, i-7), i+7] (centred, truncated at edges)",
      values: residual,
    },
  ];
  const stats = channels.map((c) => {
    const m = L.med(c.values);
    const mad = L.med(c.values.map((v) => Math.abs(v - m))) || 1e-9;
    const spread = (3.5 * mad) / 0.6745;
    return {
      channel: c.key,
      label: c.label,
      unit: c.unit,
      input: c.input,
      median: m,
      mad,
      expected_low: m - spread,
      expected_high: m + spread,
      ...(c.key === "soh" ? { input_values: c.values } : {}),
      z: c.values.map((v) => (0.6745 * (v - m)) / mad),
    };
  });
  // Sanity: the exporter's view of the detector reproduces the prototype's own events exactly.
  const flagged = stats.flatMap((s) =>
    s.z.flatMap((z, i) =>
      Math.abs(z) > 3.5 ? [`${s.channel}:${i}:${z}`] : [],
    ),
  );
  const legacy = L.AN.map((a) => `${a.k}:${a.c}:${a.z}`);
  assert(
    JSON.stringify([...flagged].sort()) === JSON.stringify([...legacy].sort()),
    "flagged set equals legacy AN",
  );

  const events = L.AN.map((a) => ({
    cycle: a.c,
    channel: a.k,
    type: a.t,
    value: a.v,
    unit: a.u,
    expected_low: a.lo,
    expected_high: a.hi,
    z: a.z,
    severity: a.sev === "h" ? "high" : "medium",
  }));
  const detected = (k) =>
    events.filter((e) => e.channel === k).map((e) => e.cycle);
  return {
    meta: meta(
      "anomalies",
      "Robust z-score (median/MAD) anomaly detection, captured as-is.",
      {
        provenance: "fitted",
        source: ["legacy/core.js:74-103"],
        units: {
          value: "channel unit",
          z: "robust standard deviations",
          median: "channel unit",
          mad: "channel unit",
        },
        known_issues: {
          F1: KNOWN_ISSUES.F1,
          F2: KNOWN_ISSUES.F2,
          F7: KNOWN_ISSUES.F7,
        },
      },
    ),
    method: {
      z: "0.6745 * (value - median) / MAD",
      mad: "median(|value - median|), replaced by 1e-9 if 0",
      flag_threshold_abs_z: 3.5,
      high_severity_abs_z: 6,
      expected_range: "median -/+ 3.5 * MAD / 0.6745",
      event_order:
        "detected per channel (temp, volt, soh), then stable-sorted by cycle",
    },
    channels: stats,
    events,
    ground_truth_vs_detected: {
      temp: { injected: [90, 170, 251], detected: detected("temp") },
      volt: { injected: [130, 271], detected: detected("volt") },
      soh: { injected: [], detected: detected("soh") },
    },
    summary: {
      total: events.length,
      high: events.filter((e) => e.severity === "high").length,
      medium: events.filter((e) => e.severity === "medium").length,
    },
  };
}

function buildSimulator(L) {
  const { P, BASE } = L;
  const SAMPLE_N = [0, 1, 10, 50, 100, 200, 300, 500, 600, 1000, 1500];
  const scenario = (name, change, note) => {
    const p = { ...P, ...change };
    const bp = { ...p, ...BASE };
    const n = p.N;
    const cs = L.eolN(p);
    const cb = L.eolN(bp);
    const dl = cs != null && cb != null ? cs - cb : null;
    return {
      name,
      ...(note ? { note } : {}),
      params: p,
      rate_pct_per_cycle: L.rate(p),
      cycles_to_eol: cs,
      soh_at: SAMPLE_N.map((k) => [k, L.sohAt(p, k)]),
      comparison_vs_baseline: {
        baseline_params: bp,
        baseline_cycles_to_eol: cb,
        delta_cycles: dl,
        delta_pct: dl == null ? null : (dl / cb) * 100,
        soh_after_n: L.sohAt(p, n),
        baseline_soh_after_n: L.sohAt(bp, n),
      },
    };
  };
  const sliders = L.SL.map(([key, label, min, max, step, unit]) => ({
    key,
    label,
    min,
    max,
    step,
    unit,
  }));
  const extremes = sliders.flatMap((s) => [
    scenario(`${s.key}_min`, { [s.key]: s.min }),
    scenario(`${s.key}_max`, { [s.key]: s.max }),
  ]);
  const traj = (p) => range(0, p.N).map((k) => L.sohAt(p, k));
  const baselineP = { ...P, ...BASE };
  const rul = L.rulAt(P.E);
  return {
    meta: meta(
      "simulator",
      "Semi-empirical what-if simulator with ASSUMED stress coefficients.",
      {
        provenance: "simulated",
        coefficient_provenance: {
          base_fade: "fitted",
          temperature: "assumed",
          c_rate: "assumed",
          dod: "assumed",
          acceleration: "assumed",
        },
        source: [
          "legacy/core.js:104-116",
          "legacy/core.js:402-409",
          "legacy/ui.js:467-547",
        ],
        units: {
          T: "°C",
          C: "C-rate",
          D: "% depth of discharge",
          N: "cycles",
          S: "% initial SOH",
          E: "% end-of-life SOH",
          rate_pct_per_cycle: "% SOH per cycle",
          cycles_to_eol:
            "cycles (null when SOH never reaches E within 5000 cycles)",
          soh_at: "[cycle, % SOH] pairs, unclamped (the chart clamps at 0)",
          delta_pct: "% change vs baseline cycles_to_eol",
        },
        known_issues: { F4: KNOWN_ISSUES.F4 },
      },
    ),
    model: {
      rate: "base_fade * exp(0.06*(T-25)) * (1 + 0.4*(C-1)) * (D/80)^0.9",
      soh: "S - rate * n * (1 + n/1500)",
      cycles_to_eol:
        "smallest integer n in [0, 5000] with soh(n) <= E, else null",
      comparison:
        "delta_cycles = cycles_to_eol - baseline_cycles_to_eol; delta_pct = delta_cycles / baseline * 100 [ui.js:545-547]",
      coefficients: {
        temp_exp_per_c: 0.06,
        c_rate_linear: 0.4,
        dod_exponent: 0.9,
        acceleration_cycles: 1500,
        eol_scan_max_cycles: 5000,
      },
    },
    base_fade_pct_per_cycle: L.fade,
    baseline_conditions: BASE,
    default_params: P,
    default_params_note: "S = round(soh_now * 10) / 10",
    sliders,
    consistency_check_F4: {
      overview_rul_cycles_at_default_eol: rul,
      simulator_baseline_cycles_to_eol: L.eolN(baselineP),
    },
    scenarios: [
      scenario("default", {}),
      scenario("baseline", { ...BASE }),
      ...extremes,
      scenario("harsh", { T: 45, C: 3, D: 100 }),
      scenario("gentle", { T: 5, C: 0.5, D: 20 }),
      scenario(
        "start_below_eol",
        { S: 70, E: 80 },
        "SOH already below EOL: cycles_to_eol is 0, delta_pct is NaN (0/0)",
      ),
      scenario(
        "beyond_horizon",
        { T: -20, C: 0.5, D: 20, S: 100, E: 60 },
        "Outside slider ranges; EOL not reached within 5000 cycles -> null",
      ),
    ],
    trajectories: [
      { name: "default", params: P, soh: traj(P) },
      { name: "baseline", params: baselineP, soh: traj(baselineP) },
    ],
  };
}

function buildAdvisor(L) {
  const { P, BASE } = L;
  const CHANGES = [
    ["Cooler: 15 °C", { T: 15 }],
    ["Warmer: 35 °C", { T: 35 }],
    ["Gentler charge: 0.5C", { C: 0.5 }],
    ["Fast charge: 2C", { C: 2 }],
    ["Shallower cycles: 60% DoD", { D: 60 }],
    ["Full-depth cycles: 100% DoD", { D: 100 }],
  ];
  const table = (p0) => {
    const b = L.eolN({ ...p0, ...BASE });
    return {
      start_soh_pct: p0.S,
      eol_pct: p0.E,
      baseline_cycles_to_eol: b,
      rows: CHANGES.map(([label, change]) => {
        const n = L.eolN({ ...p0, ...BASE, ...change });
        const dUi = n && b ? ((n - b) / b) * 100 : 0; // legacy/ui.js:658
        const dCore = n && b ? ((n - b) / b) * 100 : null; // legacy/core.js:254
        const wd = Math.min(50, Math.abs(dUi) / 2); // legacy/ui.js:659
        return {
          change: label,
          params_override: change,
          cycles_to_eol: n,
          delta_pct_ui: dUi,
          delta_pct_core: dCore,
          bar: { left_pct: dUi >= 0 ? 50 : 50 - wd, width_pct: wd },
        };
      }),
    };
  };
  return {
    meta: meta(
      "advisor",
      "Charging Advisor one-factor sensitivity on the simulator (assumed coefficients).",
      {
        provenance: "simulated",
        source: ["legacy/ui.js:624-666", "legacy/core.js:249-266"],
        units: {
          cycles_to_eol: "cycles",
          delta_pct: "% vs baseline cycles_to_eol",
          bar: "% of bar width",
        },
        known_issues: { F8: KNOWN_ISSUES.F8 },
        notes: [
          "Row formulas are transcribed from the page renderers, which compute them inline.",
          "Baseline is 25 °C, 1C, 80% DoD starting from the default initial SOH.",
        ],
      },
    ),
    default: table(P),
    edge_start_below_eol: table({ ...P, S: 70 }),
  };
}

function buildInsights(L) {
  const early = -L.lin(
    L.D.slice(0, 160).map((d) => d.i),
    L.D.slice(0, 160).map((d) => d.soh),
  ).s;
  const accelerated = L.fade > early * 1.2;
  return {
    meta: meta("insights", "Rule-based insight strings, captured verbatim.", {
      provenance: "fitted",
      source: [
        "legacy/core.js:277-291",
        "legacy/ui.js:196-199",
        "legacy/ui.js:228",
      ],
      units: { fade_pct_per_cycle: "% SOH per cycle" },
      known_issues: { F5: KNOWN_ISSUES.F5 },
    }),
    inputs: {
      first_soh_pct: L.D[0].soh,
      soh_now_pct: L.sohNow,
      n_cycles: L.N,
      first_half_fade_pct_per_cycle: early,
      recent_fade_pct_per_cycle: L.fade,
      temp_events: L.AN.filter((a) => a.k === "temp").length,
      volt_events: L.AN.filter((a) => a.k === "volt").length,
      backtest_mae: L.BT.mae,
    },
    insights: [...L.insights()],
    overview_hero: {
      rule: "fade > first_half_fade * 1.2 [legacy/ui.js:228]",
      accelerated,
      appended_text: accelerated
        ? " Fade has accelerated over the cell’s life, so the true remaining life may be shorter than a linear fit implies."
        : "",
    },
  };
}

function buildDisplayRules(L) {
  const probes = [100, 95, 90, 89.99, 85.5, 85, 84.99, 82, 80, 79.99, 50, 0];
  return {
    meta: meta(
      "display_rules",
      "Health colour and condition labels used across pages.",
      {
        provenance: "assumed",
        source: ["legacy/core.js:166-175"],
        units: { soh_pct: "%" },
        definitions: {
          colour:
            "soh >= 85 -> var(--gr); soh >= 80 -> var(--am); else var(--rd)",
          condition:
            ">= 90 Healthy; >= 85 Good; >= 80 Approaching end-of-life threshold; else Below threshold",
        },
      },
    ),
    cases: probes.map((s) => ({
      soh_pct: s,
      colour: L.hcol(s),
      condition: L.cond(s),
    })),
    current: {
      soh_pct: L.sohNow,
      colour: L.hcol(L.sohNow),
      condition: L.cond(L.sohNow),
    },
  };
}

/* ------------------------------------------------------------------------------------------ */
/* Generation                                                                                  */
/* ------------------------------------------------------------------------------------------ */

const BUILDERS = [
  ["dataset.json", buildDataset],
  ["prng.json", buildPrng],
  ["regression.json", buildRegression],
  ["soh_rul.json", buildSohRul],
  ["backtest.json", buildBacktest],
  ["anomalies.json", buildAnomalies],
  ["simulator.json", buildSimulator],
  ["advisor.json", buildAdvisor],
  ["insights.json", buildInsights],
  ["display_rules.json", buildDisplayRules],
];

/** Generate every fixture in a fresh sandbox. Returns an ordered { filename: text } map. */
function generate() {
  const L = loadLegacy();
  const out = {};
  for (const [file, build] of BUILDERS) out[file] = toJson(build(L)) + "\n";

  const legacySources = {};
  for (const f of LEGACY_SOURCES)
    legacySources[`legacy/${f}`] = sha256(
      fs.readFileSync(path.join(LEGACY_DIR, f)),
    );
  const fixtures = {};
  for (const f of Object.keys(out))
    fixtures[f] = sha256(Buffer.from(out[f], "utf8"));
  out["manifest.json"] =
    toJson({
      meta: meta(
        "manifest",
        "Index of golden fixtures and the legacy sources they were generated from.",
        {
          generator: "legacy/tools/export_golden.js",
          exporter_version: EXPORTER_VERSION,
          regenerate: "node legacy/tools/export_golden.js",
          verify: "node legacy/tools/export_golden.js --check",
          non_finite_encoding:
            'NaN, Infinity and -Infinity are stored as the strings "NaN", "Infinity", "-Infinity"',
        },
      ),
      dataset_id: "synthetic-v1",
      legacy_sources_sha256: legacySources,
      fixtures_sha256: fixtures,
      known_issues: KNOWN_ISSUES,
    }) + "\n";
  return out;
}

function writeAll(files, dir) {
  fs.mkdirSync(dir, { recursive: true });
  for (const [name, text] of Object.entries(files))
    fs.writeFileSync(path.join(dir, name), text, "utf8");
}

/** Returns a list of human-readable problems (empty when everything is consistent). */
function check(dir = DEFAULT_OUT_DIR) {
  const problems = [];
  const a = generate();
  const b = generate();
  for (const name of Object.keys(a))
    if (a[name] !== b[name])
      problems.push(`non-deterministic: ${name} differs between two runs`);
  for (const [name, text] of Object.entries(a)) {
    const p = path.join(dir, name);
    if (!fs.existsSync(p)) problems.push(`missing fixture: ${name}`);
    else if (fs.readFileSync(p, "utf8") !== text)
      problems.push(`stale fixture: ${name} does not match a fresh export`);
  }
  if (fs.existsSync(dir)) {
    for (const f of fs.readdirSync(dir))
      if (f.endsWith(".json") && !(f in a))
        problems.push(`unexpected fixture file: ${f}`);
  }
  return problems;
}

function main(argv) {
  if (argv.includes("--check")) {
    const problems = check();
    if (problems.length) {
      console.error("Golden fixture check FAILED:\n  " + problems.join("\n  "));
      console.error(
        "If a legacy change is intentional, regenerate with: node legacy/tools/export_golden.js",
      );
      return 1;
    }
    console.log(
      `Golden fixtures OK: two independent runs identical and ${Object.keys(generate()).length} committed files match.`,
    );
    return 0;
  }
  const i = argv.indexOf("--out");
  const dir = i >= 0 ? path.resolve(argv[i + 1] || "") : DEFAULT_OUT_DIR;
  const files = generate();
  writeAll(files, dir);
  console.log(
    `Wrote ${Object.keys(files).length} fixtures to ${path.relative(process.cwd(), dir) || "."}`,
  );
  return 0;
}

module.exports = {
  generate,
  check,
  toJson,
  DEFAULT_OUT_DIR,
  LEGACY_SOURCES,
  EXPORTER_VERSION,
};

if (require.main === module) process.exitCode = main(process.argv.slice(2));
