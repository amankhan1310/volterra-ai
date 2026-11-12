const BRAND = "VOLTERRA AI";
document.getElementById("brand").innerHTML =
  BRAND +
  "<small>Intelligent Battery Health &amp; Predictive Analytics</small>";
/* ---------- Seeded simulated demo dataset (deterministic) ---------- */
function rng(a) {
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const R = rng(7),
  gn = () => (R() + R() + R() - 1.5) * 1.15,
  N = 320,
  NOM = 2.0;
const D = Array.from({ length: N }, (_, i) => {
  const cap = NOM * (1 - 0.00028 * i - 0.0000005 * i * i) + gn() * 0.004;
  return {
    i,
    cap,
    soh: (cap / NOM) * 100,
    temp:
      24 +
      3 * Math.sin(i / 22) +
      gn() * 0.6 +
      ([90, 170, 251].includes(i) ? 9 : 0),
    volt: 3.72 - 0.0002 * i + gn() * 0.01 - ([130, 271].includes(i) ? 0.18 : 0),
  };
});
const col = (k) => D.map((d) => d[k]);
/* ---------- Analytics ---------- */
function lin(xs, ys) {
  const n = xs.length,
    mx = xs.reduce((a, b) => a + b) / n,
    my = ys.reduce((a, b) => a + b) / n;
  let sxx = 0,
    sxy = 0;
  xs.forEach((x, k) => {
    sxx += (x - mx) ** 2;
    sxy += (x - mx) * (ys[k] - my);
  });
  const s = sxy / sxx,
    b = my - s * mx;
  const sd = Math.sqrt(
    ys.reduce((a, y, k) => a + (y - b - s * xs[k]) ** 2, 0) / (n - 2),
  );
  return { s, b, sd, se: sd / Math.sqrt(sxx) };
}
const med = (a) => {
  const s = [...a].sort((x, y) => x - y),
    m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const W0 = N - 120,
  F = lin(
    D.slice(W0).map((d) => d.i),
    D.slice(W0).map((d) => d.soh),
  );
const sohNow = F.b + F.s * (N - 1),
  fade = -F.s;
const rulAt = (e, s = F.s) => (s < 0 ? Math.max(0, (sohNow - e) / -s) : null);
/* backtest: fit on cycles 100-219, predict 220-319 (time-ordered hold-out) */
const BT = (() => {
  const f = lin(
    D.slice(100, 220).map((d) => d.i),
    D.slice(100, 220).map((d) => d.soh),
  );
  const e = D.slice(220).map((d) => Math.abs(f.b + f.s * d.i - d.soh));
  return { mae: e.reduce((a, b) => a + b) / e.length };
})();
function anomalies() {
  const out = [];
  const chk = (k, lab, vals, unit) => {
    const m = med(vals),
      mad = med(vals.map((v) => Math.abs(v - m))) || 1e-9,
      sp = (3.5 * mad) / 0.6745;
    vals.forEach((v, i) => {
      const z = (0.6745 * (v - m)) / mad;
      if (Math.abs(z) > 3.5)
        out.push({
          c: i,
          t: lab,
          v,
          lo: m - sp,
          hi: m + sp,
          z,
          u: unit,
          sev: Math.abs(z) > 6 ? "h" : "m",
          k,
        });
    });
  };
  chk("temp", "Temperature excursion", col("temp"), "°C");
  chk("volt", "Voltage dip/spike", col("volt"), "V");
  const soh = col("soh"),
    res = soh.map((v, i) => v - med(soh.slice(Math.max(0, i - 7), i + 8)));
  chk("soh", "Irregular capacity step", res, "% resid.");
  return out.sort((a, b) => a.c - b.c);
}
const AN = anomalies();
/* ---------- Semi-empirical simulator (ASSUMED coefficients, not fitted) ---------- */
const BASE = { T: 25, C: 1, D: 80 },
  rate = (p) =>
    fade *
    Math.exp(0.06 * (p.T - 25)) *
    (1 + 0.4 * (p.C - 1)) *
    Math.pow(p.D / 80, 0.9);
const sohAt = (p, n) => p.S - rate(p) * n * (1 + n / 1500);
const eolN = (p) => {
  for (let n = 0; n <= 5000; n++) if (sohAt(p, n) <= p.E) return n;
  return null;
};
let P = { T: 25, C: 1, D: 80, N: 600, S: Math.round(sohNow * 10) / 10, E: 80 },
  saved = [];
/* ---------- Chart helper ---------- */
function chart(ss, o = {}) {
  const Wd = 720,
    H = o.h || 250,
    p = { l: 44, r: 12, t: 10, b: 22 };
  const all = ss.flatMap((s) => s.d.filter((v) => v != null));
  let lo = o.min ?? Math.min(...all),
    hi = o.max ?? Math.max(...all);
  const pd = (hi - lo) * 0.08 || 1;
  if (o.min == null) lo -= pd;
  if (o.max == null) hi += pd;
  const n = o.n || Math.max(...ss.map((s) => s.d.length)),
    X = (i) => p.l + (i / (n - 1)) * (Wd - p.l - p.r),
    Y = (v) => H - p.b - ((v - lo) / (hi - lo)) * (H - p.t - p.b);
  let g = "";
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4,
      y = Y(v);
    g += `<line x1="${p.l}" x2="${Wd - p.r}" y1="${y}" y2="${y}" stroke="var(--bd)"/><text x="${p.l - 6}" y="${y + 4}" text-anchor="end" fill="var(--mu)" font-size="11">${v.toFixed(o.dp ?? 1)}</text>`;
  }
  g += `<text x="${p.l}" y="${H - 5}" fill="var(--mu)" font-size="11">0</text><text x="${Wd - p.r}" y="${H - 5}" text-anchor="end" fill="var(--mu)" font-size="11">cycle ${n - 1}</text>`;
  if (o.v != null)
    g += `<line x1="${X(o.v)}" x2="${X(o.v)}" y1="${p.t}" y2="${H - p.b}" stroke="var(--mu)" stroke-dasharray="2 4"/>`;
  ss.forEach((s) => {
    let d = "",
      pen = 0;
    s.d.forEach((v, i) => {
      if (v == null) {
        pen = 0;
        return;
      }
      d += (pen ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1);
      pen = 1;
    });
    g += `<path d="${d}" fill="none" stroke="${s.c}" stroke-width="${s.w || 2}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""} stroke-linejoin="round"/>`;
  });
  (o.marks || []).forEach(
    (m) =>
      (g += `<circle cx="${X(m.x)}" cy="${Y(m.y)}" r="4.5" fill="${m.c}" stroke="var(--card)" stroke-width="1.5"><title>${m.t || ""}</title></circle>`),
  );
  return `<svg viewBox="0 0 ${Wd} ${H}" role="img" aria-label="${o.a || "chart"}">${g}</svg>`;
}
const leg = (a) =>
  `<div class="leg">${a.map((x) => `<span><i style="background:${x[1]}"></i>${x[0]}</span>`).join("")}</div>`;
const tip = (t, x) =>
  `<span title="${t}" style="cursor:help;border-bottom:1px dotted var(--mu)">${x}</span>`;
const kpi = (l, v, u, t, c) =>
  `<div class="card"><div class="mu">${tip(t, l)}</div><div class="big" style="color:${c || "var(--tx)"}">${v}<small>${u}</small></div></div>`;
const hcol = (s) =>
  s >= 85 ? "var(--gr)" : s >= 80 ? "var(--am)" : "var(--rd)";
const cond = (s) =>
  s >= 90
    ? "Healthy"
    : s >= 85
      ? "Good"
      : s >= 80
        ? "Approaching end-of-life threshold"
        : "Below threshold";
/* ---------- Pages ---------- */
var head = (t, s) =>
  `<div class="top"><div><h1>${t}</h1><p class="mu">${s}</p></div><div><span class="tag s">SIMULATED DEMO DATASET · seeded</span> <button class="btn o" onclick="go(cur)">Reset view</button></div></div>`;
const pages = {
  overview() {
    const rul = rulAt(P.E),
      lo = rulAt(P.E, F.s - 1.96 * F.se),
      hi = rulAt(P.E, F.s + 1.96 * F.se),
      ext = Math.min(N + Math.ceil((rul || 200) * 1.4), N + 500);
    const fc = Array(ext).fill(null);
    for (let i = N - 1; i < ext; i++) fc[i] = F.b + F.s * i;
    const C = 2 * Math.PI * 70;
    return (
      head(
        "Battery Intelligence Center",
        "Understand battery health today. Predict degradation tomorrow.",
      ) +
      `<div class="card hero"><svg width="180" height="180" viewBox="0 0 180 180" role="img" aria-label="SOH gauge"><circle cx="90" cy="90" r="70" fill="none" stroke="var(--el)" stroke-width="14"/><circle class="arc" id="arc" cx="90" cy="90" r="70" fill="none" stroke="${hcol(sohNow)}" stroke-width="14" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C}" transform="rotate(-90 90 90)"/><text x="90" y="92" text-anchor="middle" fill="var(--tx)" font-size="34" font-weight="800">${sohNow.toFixed(1)}%</text><text x="90" y="114" text-anchor="middle" fill="var(--mu)" font-size="12">State of Health</text></svg>
 <div style="flex:1;min-width:240px"><h2>${cond(sohNow)}</h2><p class="mu">SOH = capacity ÷ ${NOM.toFixed(1)} Ah reference, trend-fitted over the last 120 cycles.</p>
 <p style="margin-top:12px"><span class="big" style="color:var(--cy)">${rul ? Math.round(rul) : "n/a"}<small>cycles RUL to ${P.E}% SOH</small></span></p>
 <p class="mu">${tip("Linear fit slope ±1.96 standard errors. Quantifies fit uncertainty only, not model-form error.", "95% fit interval")}: ${lo ? Math.round(lo) : "–"} to ${hi ? Math.round(hi) : "–"} cycles · ${tip("Mean absolute error of a straight-line forecast on the held-out final 100 cycles (fit on cycles 100–219).", "time-ordered backtest MAE")} ${BT.mae.toFixed(2)} SOH points</p>
 <p style="margin-top:8px"><span class="tag s">Simulated</span> <span class="tag f">Fitted</span> <span class="tag p">Predicted</span></p></div></div>
 <div class="grid g3" style="margin:14px 0">${kpi("SOH", sohNow.toFixed(1), "%", "Capacity relative to the reference capacity.", hcol(sohNow))}${kpi("Capacity", D[N - 1].cap.toFixed(3), "Ah", "Latest cycle discharge capacity (simulated).")}${kpi("Temperature", D[N - 1].temp.toFixed(1), "°C", "Latest cycle mean temperature (simulated).")}${kpi("Voltage", D[N - 1].volt.toFixed(2), "V", "Latest cycle mean voltage (simulated).")}${kpi("Cycles", N, "", "Charge/discharge cycles in the dataset.")}${kpi("Fade rate", fade.toFixed(3), "%/cycle", "Recent SOH loss per cycle from the linear fit.")}</div>
 <div class="grid g2"><div class="card"><h2>Degradation timeline</h2>${chart(
   [
     { d: col("soh"), c: "var(--gr)" },
     { d: fc, c: "var(--cy)", dash: "6 5" },
     { d: Array(ext).fill(P.E), c: "var(--rd)", dash: "2 4", w: 1.2 },
   ],
   { v: N - 1, a: "SOH history and forecast" },
 )}${leg([
   ["Observed (simulated)", "var(--gr)"],
   ["Forecast (linear fit)", "var(--cy)"],
   [`EOL ${P.E}%`, "var(--rd)"],
 ])}<p class="mu">Dotted vertical line marks the prediction boundary.</p></div>
 <div class="card"><h2>Intelligence insights</h2>${insights()
   .map((t) => `<p style="margin:8px 0">• ${t}</p>`)
   .join("")}</div></div>
 <div class="card" style="margin-top:14px"><h2>Telemetry explorer</h2><div id="tsel" style="margin-bottom:8px"></div><div id="tchart"></div></div>`
    );
  },
  digital() {
    return (
      head(
        "Battery Digital Twin",
        "A software representation driven by the selected cycle of the dataset — not connected to any vehicle.",
      ) +
      `<div class="grid g2"><div class="card"><svg id="pack" viewBox="0 0 360 250" role="img" aria-label="Battery pack modules"></svg><label>Cycle <span id="cv"></span></label><input type="range" id="cs" min="0" max="${N - 1}" value="${N - 1}"><div style="margin-top:10px"><button class="btn o" id="m1">Color by SOH</button> <button class="btn o" id="m2">Color by temperature</button></div></div>
 <div class="card" id="tinfo"></div></div><div class="note">The dataset has pack-level measurements only. The 24 modules are drawn uniformly from the pack value; nothing per-cell is measured, so module readings are illustrative.</div>`
    );
  },
  sim() {
    return (
      head(
        "What-If Simulator",
        "Compare operating scenarios against the 25 °C, 1C, 80% DoD baseline.",
      ) +
      `<div class="grid g2"><div class="card"><h2>Scenario inputs</h2><div id="ctl"></div><div style="margin-top:14px"><button class="btn" id="sv">Save scenario</button> <button class="btn o" id="rs">Reset controls</button></div><div id="sl" style="margin-top:10px"></div></div>
 <div class="card" id="simout"></div></div><div class="note">Model: SOH(n) = SOH₀ − r·n·(1 + n/1500), r = recent fitted fade × e^(0.06·(T−25)) × (1 + 0.4·(C−1)) × (DoD/80)^0.9. Temperature, C-rate and DoD coefficients are assumed, illustrative values, not fitted to data. Outputs are simulated estimates.</div>`
    );
  },
  anom() {
    return (
      head(
        "Anomaly Detection",
        "Robust z-score (median/MAD) with a ±3.5 threshold. Flags unusual points, not confirmed faults.",
      ) +
      `<div class="grid g3" style="margin-bottom:14px">${kpi("Events flagged", AN.length, "", "All detections")}${kpi("High severity", AN.filter((a) => a.sev == "h").length, "", "|z| > 6", "var(--rd)")}${kpi("Medium severity", AN.filter((a) => a.sev == "m").length, "", "3.5 < |z| ≤ 6", "var(--am)")}</div>
 <div class="grid g2"><div class="card"><h2>Temperature</h2>${chart([{ d: col("temp"), c: "var(--cy)", w: 1.5 }], { marks: AN.filter((a) => a.k == "temp").map((a) => ({ x: a.c, y: a.v, c: "var(--rd)", t: "Cycle " + a.c })), a: "Temperature anomalies" })}</div>
 <div class="card"><h2>Voltage</h2>${chart([{ d: col("volt"), c: "var(--gr)", w: 1.5 }], { dp: 2, marks: AN.filter((a) => a.k == "volt").map((a) => ({ x: a.c, y: a.v, c: "var(--rd)", t: "Cycle " + a.c })), a: "Voltage anomalies" })}</div></div>
 <div class="card wrap" style="margin-top:14px"><h2>Detected events</h2>${AN.length ? `<table><tr><th>Cycle</th><th>Type</th><th>Value</th><th>Expected range</th><th>Severity</th></tr>${AN.map((a) => `<tr><td>${a.c}</td><td>${a.t}</td><td>${a.v.toFixed(a.k == "volt" ? 3 : 2)} ${a.u}</td><td>${a.lo.toFixed(2)} to ${a.hi.toFixed(2)}</td><td class="sev ${a.sev}">${a.sev == "h" ? "High" : "Medium"}</td></tr>`).join("")}</table>` : '<p class="mu">No anomalies detected at this threshold.</p>'}<p class="mu">Why flagged: the value sits more than 3.5 robust standard deviations from the series median. Investigate before concluding a fault.</p></div>`
    );
  },
  advisor() {
    const b = eolN({ ...P, ...BASE }),
      row = (l, ch, why) => {
        const q = { ...P, ...BASE, ...ch },
          n = eolN(q),
          d = n && b ? ((n - b) / b) * 100 : null;
        return `<tr><td>${l}</td><td>${n ?? ">5000"}</td><td style="color:${d > 0 ? "var(--gr)" : d < 0 ? "var(--rd)" : "var(--mu)"}">${d == null ? "–" : (d > 0 ? "+" : "") + d.toFixed(0) + "%"}</td><td class="mu">${why}</td></tr>`;
      };
    return (
      head(
        "Charging Advisor",
        "Model-based sensitivity: how each change moves cycles to end-of-life under the simulator’s assumptions.",
      ) +
      `<div class="card wrap"><table><tr><th>Change from baseline</th><th>Cycles to ${P.E}% SOH</th><th>Δ vs baseline</th><th>Direction (plain language)</th></tr>
 <tr><td>Baseline (25 °C, 1C, 80% DoD)</td><td>${b ?? ">5000"}</td><td>–</td><td class="mu">Reference</td></tr>
 ${row("Cooler: 15 °C", { T: 15 }, "Lower temperature slows modelled fade")}${row("Warmer: 35 °C", { T: 35 }, "Heat accelerates modelled fade")}${row("Gentler charge: 0.5C", { C: 0.5 }, "Slower charging reduces stress")}${row("Fast charge: 2C", { C: 2 }, "Faster charging increases stress")}${row("Shallower cycles: 60% DoD", { D: 60 }, "Less depth per cycle is gentler")}${row("Full-depth cycles: 100% DoD", { D: 100 }, "Deeper cycles wear faster")}</table>
 <div class="note">Percentages come from the simulator’s assumed coefficients using SOH₀ ${P.S}%. They show direction and relative size under the model, not guaranteed battery-life gains.</div></div>`
    );
  },
  about() {
    return (
      head("About", "Project information") +
      `<div class="card"><h2>${BRAND}</h2><p>An AI-powered software platform for EV battery health estimation, degradation analysis, Remaining Useful Life prediction, anomaly detection, and scenario-based battery intelligence using public and simulated battery data.</p><p class="mu">Academic software prototype. It does not replace a manufacturer’s Battery Management System, professional diagnostics or warranty assessment.</p>
 <h2 style="margin-top:16px">State of Charge, Health and Remaining Useful Life</h2><p class="mu">SOC is the present charge level. SOH is condition relative to a reference (here: capacity ÷ ${NOM} Ah). RUL is an estimate of cycles remaining before a chosen end-of-life criterion — not a guaranteed replacement date.</p>
 <h2 style="margin-top:16px">What is real in this build</h2><p class="mu">Dataset: seeded synthetic cycles (${N}), reproducible. Computed live in your browser: SOH, linear trend fit, RUL with fit interval, hold-out backtest, robust z-score anomaly detection, scenario simulation. Not included: CSV upload, Python backend, PDF reports, 3D twin, ML model comparison.</p></div>`
    );
  },
};
function insights() {
  const t = col("temp"),
    r = lin(t, col("soh")),
    k = AN.filter((a) => a.k == "temp").length,
    v = AN.filter((a) => a.k == "volt").length;
  return [
    `Capacity fell from ${D[0].soh.toFixed(1)}% to ${sohNow.toFixed(1)}% SOH over ${N} cycles; recent fade is ${fade.toFixed(3)} %/cycle.`,
    `Fade is accelerating: first-half ${(-lin(
      D.slice(0, 160).map((d) => d.i),
      D.slice(0, 160).map((d) => d.soh),
    ).s).toFixed(3)} vs last-120 ${fade.toFixed(3)} %/cycle.`,
    `${k} temperature and ${v} voltage events were flagged. With so few events there is insufficient evidence to link them to degradation (correlation ≠ causation).`,
    `The straight-line forecast has a hold-out MAE of ${BT.mae.toFixed(2)} SOH points; treat the RUL as an estimate.`,
  ];
}
/* ---------- Page wiring ---------- */
const names = {
  overview: "Overview",
  digital: "Digital Twin",
  sim: "What-If Simulator",
  anom: "Anomaly Detection",
  advisor: "Charging Advisor",
  about: "About",
};
let cur = "overview";
document.getElementById("nav").innerHTML = Object.entries(names)
  .map(([k, v]) => `<button data-k="${k}">${v}</button>`)
  .join("");
document.getElementById("nav").onclick = (e) => {
  if (e.target.dataset.k) go(e.target.dataset.k);
};
function go(k) {
  cur = k;
  location.hash = k;
  document
    .querySelectorAll("nav button")
    .forEach(
      (b) =>
        b.toggleAttribute("aria-current", b.dataset.k == k) &&
        b.setAttribute("aria-current", "page"),
    );
  document.querySelectorAll("nav button").forEach((b) => {
    if (b.dataset.k != k) b.removeAttribute("aria-current");
  });
  const m = document.getElementById("main");
  m.innerHTML = pages[k]();
  m.scrollTop = 0;
  ({ overview: ovInit, digital: twInit, sim: simInit })[k]?.();
}
function ovInit() {
  requestAnimationFrame(() => {
    const a = document.getElementById("arc");
    if (a) a.style.strokeDashoffset = 2 * Math.PI * 70 * (1 - sohNow / 100);
  });
  const M = {
    soh: ["SOH (%)", "var(--gr)", 1],
    temp: ["Temperature (°C)", "var(--cy)", 1],
    volt: ["Voltage (V)", "var(--am)", 2],
    cap: ["Capacity (Ah)", "var(--gr)", 3],
  };
  let sel = "soh";
  const draw = () => {
    document.getElementById("tsel").innerHTML = Object.entries(M)
      .map(
        ([k, m]) =>
          `<button class="btn ${k == sel ? "" : "o"}" data-m="${k}" style="margin-right:6px">${m[0]}</button>`,
      )
      .join("");
    document.getElementById("tchart").innerHTML = chart(
      [{ d: col(sel), c: M[sel][1], w: 1.6 }],
      { dp: M[sel][2], a: M[sel][0] },
    );
  };
  draw();
  document.getElementById("tsel").onclick = (e) => {
    if (e.target.dataset.m) {
      sel = e.target.dataset.m;
      draw();
    }
  };
}
function twInit() {
  let mode = "soh",
    pick = null;
  const cs = document.getElementById("cs");
  const draw = () => {
    const d = D[+cs.value];
    document.getElementById("cv").textContent = d.i;
    const c =
      mode == "soh"
        ? hcol(d.soh)
        : d.temp < 30
          ? "var(--cy)"
          : d.temp < 40
            ? "var(--am)"
            : "var(--rd)";
    let s =
      '<rect x="8" y="10" width="344" height="226" rx="14" fill="var(--el)" stroke="var(--bd)"/>';
    for (let k = 0; k < 24; k++) {
      const x = 22 + (k % 6) * 54,
        y = 24 + Math.floor(k / 6) * 52;
      s += `<rect class="cell" data-k="${k}" x="${x}" y="${y}" width="44" height="42" rx="6" fill="${c}" fill-opacity=".85" stroke="${pick == k ? "var(--tx)" : "none"}" stroke-width="2" tabindex="0" role="button" aria-label="Module ${k + 1}"/><text x="${x + 22}" y="${y + 26}" text-anchor="middle" font-size="11" fill="#04141a" pointer-events="none">${k + 1}</text>`;
    }
    document.getElementById("pack").innerHTML = s;
    document.getElementById("tinfo").innerHTML =
      `<h2>Pack state at cycle ${d.i}</h2><p><span class="tag s">Simulated</span> <span class="tag f">Pack-level</span></p><div class="grid" style="grid-template-columns:1fr 1fr;margin-top:10px"><div><div class="mu">SOH</div><div class="big">${d.soh.toFixed(1)}<small>%</small></div></div><div><div class="mu">Capacity</div><div class="big">${d.cap.toFixed(3)}<small>Ah</small></div></div><div><div class="mu">Temperature</div><div class="big">${d.temp.toFixed(1)}<small>°C</small></div></div><div><div class="mu">Voltage</div><div class="big">${d.volt.toFixed(2)}<small>V</small></div></div></div><p class="mu" style="margin-top:12px">${pick == null ? "Select a module to inspect it." : `Module ${pick + 1}: no cell-level measurement exists. Showing the pack value (illustrative).`}</p>${chart([{ d: col("soh"), c: "var(--gr)", w: 1.5 }], { v: d.i, h: 150, a: "SOH with selected cycle" })}`;
  };
  draw();
  cs.oninput = draw;
  m1.onclick = () => {
    mode = "soh";
    draw();
  };
  m2.onclick = () => {
    mode = "temp";
    draw();
  };
  document.getElementById("pack").onclick = (e) => {
    const k = e.target.dataset?.k;
    if (k != null) {
      pick = +k;
      draw();
    }
  };
}
const SL = [
    ["T", "Temperature", 5, 45, 1, "°C"],
    ["C", "Charge rate", 0.5, 3, 0.1, "C"],
    ["D", "Depth of discharge", 20, 100, 5, "%"],
    ["N", "Cycles to simulate", 100, 1500, 50, ""],
    ["S", "Initial SOH", 70, 100, 0.5, "%"],
    ["E", "End-of-life SOH", 60, 90, 1, "%"],
  ],
  SCol = ["var(--am)", "var(--rd)", "var(--gr)", "#B58CFF"];
function simInit() {
  ctl.innerHTML = SL.map(
    ([k, l, a, b, s, u]) =>
      `<label>${l} <span id="o${k}"></span></label><input type="range" id="i${k}" min="${a}" max="${b}" step="${s}" value="${P[k]}">`,
  ).join("");
  SL.forEach(([k, , , , , u]) => {
    const el = document.getElementById("i" + k);
    el.oninput = () => {
      P[k] = +el.value;
      simDraw();
    };
  });
  sv.onclick = () => {
    if (saved.length >= 4) return toast("Delete a scenario first (max 4).");
    saved.push({ name: "Scenario " + (saved.length + 1), p: { ...P } });
    simDraw();
  };
  rs.onclick = () => {
    P = { T: 25, C: 1, D: 80, N: 600, S: Math.round(sohNow * 10) / 10, E: 80 };
    SL.forEach(([k]) => (document.getElementById("i" + k).value = P[k]));
    simDraw();
  };
  sl.onclick = (e) => {
    const i = e.target.dataset.d,
      r = e.target.dataset.r,
      u = e.target.dataset.u;
    if (i != null) {
      saved.splice(+i, 1);
    } else if (r != null) {
      const n = prompt("Rename scenario", saved[+r].name);
      if (n) saved[+r].name = n.slice(0, 30);
    } else if (u != null) {
      saved.push({ name: saved[+u].name + " copy", p: { ...saved[+u].p } });
      saved.length > 4 && saved.pop();
    }
    simDraw();
  };
  simDraw();
}
function toast(t) {
  alert(t);
}
function simDraw() {
  SL.forEach(
    ([k, , , , , u]) =>
      (document.getElementById("o" + k).textContent =
        P[k] + (u ? " " + u : "")),
  );
  const bp = { ...P, ...BASE },
    series = (p, n) =>
      Array.from({ length: n + 1 }, (_, i) => Math.max(0, sohAt(p, i))),
    n = P.N;
  const cb = eolN(bp),
    cs = eolN(P),
    fin = sohAt(P, n),
    finB = sohAt(bp, n),
    ss = [
      { d: series(bp, n), c: "var(--mu)", dash: "5 4" },
      { d: series(P, n), c: "var(--cy)", w: 2.4 },
      ...saved.map((s, i) => ({ d: series(s.p, n), c: SCol[i], w: 1.6 })),
    ];
  const dl = (a, b) =>
    a == null || b == null ? "–" : (a - b > 0 ? "+" : "") + (a - b).toFixed(1);
  simout.innerHTML = `<h2>Results vs baseline</h2><div class="grid g3"><div class="card" style="background:var(--el)"><div class="mu">SOH after ${n} cycles</div><div class="big" style="color:var(--cy)">${fin.toFixed(1)}<small>% (${dl(fin, finB)} vs base)</small></div></div><div class="card" style="background:var(--el)"><div class="mu">Cycles to ${P.E}% SOH</div><div class="big">${cs ?? ">5000"}<small>(base ${cb ?? ">5000"})</small></div></div><div class="card" style="background:var(--el)"><div class="mu">Fade rate</div><div class="big">${rate(P).toFixed(3)}<small>%/cycle</small></div></div></div>
 ${chart(ss, { n: n + 1, min: Math.max(0, Math.min(fin, finB) - 3), max: 100, a: "Scenario SOH trajectories" })}${leg([["Baseline", "var(--mu)"], ["Current", "var(--cy)"], ...saved.map((s, i) => [s.name, SCol[i]])])}<p class="mu"><span class="tag s">Simulated estimate</span> Model uncertainty is not quantified.</p>`;
  sl.innerHTML = saved.length
    ? `<h2>Saved scenarios</h2>` +
      saved
        .map(
          (s, i) =>
            `<div style="display:flex;gap:8px;align-items:center;justify-content:space-between;padding:4px 0"><span style="color:${SCol[i]}">${s.name} <span class="mu">${s.p.T}°C · ${s.p.C}C · ${s.p.D}% DoD</span></span><span><button class="btn o" data-r="${i}">Rename</button> <button class="btn o" data-u="${i}">Duplicate</button> <button class="btn o" data-d="${i}">Delete</button></span></div>`,
        )
        .join("")
    : '<p class="mu">No saved scenarios yet. Adjust inputs, then save to overlay comparisons.</p>';
}
go(location.hash.slice(1) in pages ? location.hash.slice(1) : "overview");
