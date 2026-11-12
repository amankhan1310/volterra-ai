/* ===== Redesign layer: overrides page renderers + shell. Calculations (F, AN, rate, sohAt, eolN...) are reused untouched. ===== */
const $ = (i) => document.getElementById(i);
const IC = (p) =>
  `<svg class="ic" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICO = {
  overview: IC(
    '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  ),
  digital: IC(
    '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M12 22V12M3 7l9 5 9-5"/>',
  ),
  sim: IC(
    '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  ),
  anom: IC('<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>'),
  advisor: IC('<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>'),
  about: IC('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'),
};
$("brand").innerHTML =
  `<svg width="32" height="32" viewBox="0 0 32 32"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#54E7FF"/><stop offset="1" stop-color="#8DAFFF"/></linearGradient></defs><path d="M16 2l12 7v14l-12 7-12-7V9z" fill="none" stroke="url(#lg)" stroke-width="1.8"/><rect x="10" y="16" width="3" height="6" rx="1" fill="url(#lg)"/><rect x="14.5" y="12" width="3" height="10" rx="1" fill="url(#lg)"/><rect x="19" y="8" width="3" height="14" rx="1" fill="url(#lg)"/></svg><div class="lt"><b>${BRAND}</b><small>Battery Intelligence</small></div>`;
$("nav").innerHTML = [
  ["Monitor", ["overview", "digital", "anom"]],
  ["Plan", ["sim", "advisor"]],
  ["Project", ["about"]],
]
  .map(
    ([g, ks]) =>
      `<div class="grp nl">${g}</div>` +
      ks
        .map(
          (k) =>
            `<button data-k="${k}" title="${names[k]}">${ICO[k]}<span class="nl">${names[k]}</span></button>`,
        )
        .join(""),
  )
  .join("");
$("nav").onclick = (e) => {
  const b = e.target.closest("button");
  if (b) go(b.dataset.k);
};
$("qn").innerHTML = Object.entries(names)
  .map(([k, v]) => `<option value="${k}">${v}</option>`)
  .join("");
$("qn").onchange = (e) => go(e.target.value);
$("bn").textContent = AN.length;
$("bell").onclick = () =>
  toast(
    AN.length +
      " anomaly events flagged in the dataset. Open Anomaly Detection to review.",
  );
$("cb").onclick = () => {
  $("side").classList.toggle("min");
  setTimeout(rsz, 300);
};
$("bg").onclick = () => $("side").classList.toggle("open");
function toast(t) {
  let e = $("toast");
  if (!e) {
    e = document.createElement("div");
    e.id = "toast";
    e.className = "toast";
    e.setAttribute("role", "status");
    document.body.appendChild(e);
  }
  e.textContent = t;
  e.classList.add("on");
  clearTimeout(e._t);
  e._t = setTimeout(() => e.classList.remove("on"), 3400);
}
function rsz() {
  window.echarts &&
    document
      .querySelectorAll(".ech")
      .forEach((el) => echarts.getInstanceByDom(el)?.resize());
}
addEventListener("resize", rsz);
function runA() {
  go(cur);
  toast(
    "Analysis recomputed from the seeded dataset: SOH " +
      sohNow.toFixed(1) +
      "%, RUL " +
      Math.round(rulAt(P.E)) +
      " cycles.",
  );
}
head = (t, s) =>
  `<div class="top"><div><h1>${t}</h1><p class="mu" style="max-width:60ch">${s}</p></div><div class="ta"><button class="btn" onclick="runA()">Run analysis</button></div></div>`;
function go(k) {
  cur = k;
  location.hash = k;
  document
    .querySelectorAll("nav button")
    .forEach((b) =>
      b.dataset.k == k
        ? b.setAttribute("aria-current", "page")
        : b.removeAttribute("aria-current"),
    );
  const m = $("main");
  m.innerHTML = '<div class="pg">' + pages[k]() + "</div>";
  m.scrollTop = 0;
  ({ overview: ovInit, digital: twInit, sim: simInit })[k]?.();
  $("pt").textContent = names[k];
  $("qn").value = k;
  $("side").classList.remove("open");
}
/* ---- ECharts helpers (fallback to the original SVG chart if the CDN fails) ---- */
const eb = (xm, y0, y1, zoom, fmt, dp = 2) => ({
  animationDuration: 700,
  textStyle: { fontFamily: "Manrope,sans-serif" },
  grid: { left: 52, right: 20, top: 36, bottom: zoom ? 64 : 30 },
  tooltip: {
    trigger: "axis",
    backgroundColor: "#121A26",
    borderColor: "#1B2638",
    textStyle: { color: "#F5F7FC", fontSize: 12 },
    axisPointer: { lineStyle: { color: "#2a3b57" } },
    formatter: (ps) =>
      "Cycle " +
      Math.round(ps[0].value[0]) +
      ps
        .map(
          (p) =>
            `<br>${p.marker}${p.seriesName}: <b>${(+p.value[1]).toFixed(dp)}</b>`,
        )
        .join(""),
  },
  legend: {
    top: 0,
    right: 0,
    textStyle: { color: "#8998AD" },
    itemWidth: 14,
    itemHeight: 3,
    icon: "roundRect",
  },
  xAxis: {
    type: "value",
    min: 0,
    max: xm,
    axisLabel: { color: "#8998AD" },
    axisLine: { lineStyle: { color: "#1B2638" } },
    splitLine: { show: false },
  },
  yAxis: {
    type: "value",
    min: y0,
    max: y1,
    scale: y0 == null,
    axisLabel: { color: "#8998AD", formatter: fmt || "{value}" },
    splitLine: { lineStyle: { color: "rgba(137,152,173,.12)" } },
  },
  dataZoom: zoom
    ? [
        { type: "inside", filterMode: "none" },
        {
          type: "slider",
          height: 16,
          bottom: 6,
          borderColor: "#1B2638",
          fillerColor: "rgba(84,231,255,.12)",
          textStyle: { color: "#8998AD" },
        },
      ]
    : [],
});
function ec(id, opt, fb) {
  const el = $(id);
  if (!el) return;
  if (!window.echarts) {
    el.innerHTML =
      fb ||
      '<p class="mu">Chart library could not load (check your connection).</p>';
    return;
  }
  const c = echarts.getInstanceByDom(el) || echarts.init(el);
  c.setOption(opt, true);
  return c;
}
const area = (c) =>
  new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: c + "38" },
    { offset: 1, color: c + "00" },
  ]);
const spk = (a, c) => {
  const s = a.filter((_, i) => i % 4 == 0),
    lo = Math.min(...s),
    hi = Math.max(...s);
  return `<svg class="spk" viewBox="0 0 120 40" preserveAspectRatio="none" aria-hidden="true"><path d="${s.map((v, i) => (i ? "L" : "M") + ((i / (s.length - 1)) * 120).toFixed(1) + " " + (37 - ((v - lo) / (hi - lo || 1)) * 34).toFixed(1)).join("")}" fill="none" stroke="${c}" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
};
const xt = () => Math.min(N + Math.ceil((rulAt(P.E) || 200) * 1.4), N + 500);
/* ---- Overview ---- */
pages.overview = () => {
  const rul = rulAt(P.E),
    lo = rulAt(P.E, F.s - 1.96 * F.se),
    hi = rulAt(P.E, F.s + 1.96 * F.se),
    early = -lin(
      D.slice(0, 160).map((d) => d.i),
      D.slice(0, 160).map((d) => d.soh),
    ).s,
    C1 = 2 * Math.PI * 118,
    C2 = 2 * Math.PI * 96;
  let tk = "";
  for (let k = 0; k < 60; k++) {
    const a = (k * 6 * Math.PI) / 180,
      mj = k % 5 == 0,
      r1 = mj ? 133 : 137,
      on = k <= sohNow * 0.6;
    tk += `<line x1="${(170 + r1 * Math.sin(a)).toFixed(1)}" y1="${(170 - r1 * Math.cos(a)).toFixed(1)}" x2="${(170 + 144 * Math.sin(a)).toFixed(1)}" y2="${(170 - 144 * Math.cos(a)).toFixed(1)}" stroke="${on ? "#54E7FF" : "#2a3b57"}" stroke-opacity="${on ? 0.75 : 1}" stroke-width="${mj ? 1.6 : 1}"/>`;
  }
  const ring = (id, r, w, s, C) =>
    `<circle cx="170" cy="170" r="${r}" fill="none" stroke="#121A26" stroke-width="${w}"/><circle id="${id}" class="arc" cx="170" cy="170" r="${r}" fill="none" stroke="${s}" stroke-width="${w}" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C}"/>`;
  const ins = insights(),
    meta = [
      ["Observation", "var(--cy)"],
      ["Watch", "var(--am)"],
      ["Note", "var(--ib)"],
      ["Model", "var(--gr)"],
    ];
  const kc = (cl, l, v, u, tp, note, ex, c) =>
    `<div class="card hv ${cl}"><div class="lb">${tip(tp, l)}</div><div class="big" style="color:${c || "var(--tx)"};margin-top:8px">${v}<small>${u}</small></div>${ex || ""}<p class="mu" style="font-size:12px;margin-top:6px">${note}</p></div>`;
  return (
    head(
      "Battery Intelligence",
      "Understand degradation. Anticipate risk. Make smarter battery decisions.",
    ) +
    `<div class="card hg"><div class="hl"><svg viewBox="0 0 340 340" width="100%" style="max-width:340px" role="img" aria-label="State of health ${sohNow.toFixed(1)} percent"><defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" style="stop-color:var(--cy)"/><stop offset="1" style="stop-color:${hcol(sohNow)}"/></linearGradient></defs>${tk}<g transform="rotate(-90 170 170)">${ring("a1", 118, 12, "url(#g1)", C1)}${ring("a2", 96, 4, "#8DAFFF", C2)}</g><text x="170" y="182" text-anchor="middle" fill="#F5F7FC" font-size="58" font-weight="800">${sohNow.toFixed(1)}<tspan font-size="24" fill="#8998AD">%</tspan></text><text x="170" y="208" text-anchor="middle" fill="#8998AD" font-size="11" letter-spacing="1.5">STATE OF HEALTH</text><text x="170" y="250" text-anchor="middle" fill="#8DAFFF" font-size="10">inner ring: life used to ${P.E}% threshold</text></svg></div>
 <div class="hr"><div class="lb">Battery condition</div><div class="cnd" style="color:${hcol(sohNow)}">${cond(sohNow)}</div>
 <p class="mu" style="max-width:52ch">The estimate is a straight-line fit over the latest 120 cycles of the simulated dataset.${fade > early * 1.2 ? " Fade has accelerated over the cell’s life, so the true remaining life may be shorter than a linear fit implies." : ""}</p>
 <div style="margin-top:22px"><div class="lb">Remaining useful life</div><div class="big xl" style="color:var(--cy)">${rul ? Math.round(rul) : "n/a"}<small>cycles to ${P.E}% SOH</small></div></div>
 <div class="stats"><div><div class="lb">Fade rate</div><b>${fade.toFixed(3)} <span class="mu" style="font-size:12px">%/cycle</span></b></div><div><div class="lb">${tip("Slope ±1.96 standard errors. Captures fit noise only.", "95% fit interval")}</div><b>${lo ? Math.round(lo) : "–"}–${hi ? Math.round(hi) : "–"} <span class="mu" style="font-size:12px">cycles</span></b></div><div><div class="lb">${tip("Straight-line forecast scored on the held-out final 100 cycles.", "Backtest MAE")}</div><b>${BT.mae.toFixed(2)} <span class="mu" style="font-size:12px">SOH pts</span></b></div></div>
 <span class="tag s">Simulated data</span> <span class="tag f">Fitted: linear trend</span> <span class="tag p">Predicted</span></div></div>
 <div class="k12">${kc("s6", "Capacity", D[N - 1].cap.toFixed(3), "Ah", "Latest cycle discharge capacity (simulated).", "of " + NOM.toFixed(1) + " Ah reference", spk(col("cap"), "#7CF2BC"))}${kc("s6", "Temperature", D[N - 1].temp.toFixed(1), "°C", "Latest cycle mean temperature (simulated).", AN.filter((a) => a.k == "temp").length + " excursions flagged in history", spk(col("temp"), "#54E7FF"))}
 ${kc("s3", "Voltage", D[N - 1].volt.toFixed(2), "V", "Latest cycle mean voltage (simulated).", "drifting down with age")}${kc("s3", "Cycles", N, "", "Charge/discharge cycles in the dataset.", "seeded, reproducible")}${kc("s3", "Fade rate", fade.toFixed(3), "%/cycle", "Recent SOH loss per cycle.", "last 120 cycles")}${kc("s3", "Anomalies", AN.length, "", "Events flagged by the robust z-score detector.", AN.filter((a) => a.sev == "h").length + " high severity", null, AN.length ? "var(--am)" : "var(--tx)")}</div>
 <div class="k12"><div class="card s8"><div class="tb"><div><div class="lb">Degradation timeline</div><p class="mu" style="font-size:12.5px">Observed (simulated) vs. linear forecast</p></div><div class="seg" id="rg"><button data-r="all" class="on">Full</button><button data-r="120">Last 120</button></div></div><div id="tl" class="ech"></div></div>
 <div class="card s4"><div class="lb">Intelligence insights</div><p class="mu" style="font-size:12px;margin:2px 0 6px">Rule-based findings computed in your browser</p>${ins.map((t, i) => `<div class="in"><i style="background:${meta[i][1]}"></i><div><div class="lb" style="color:${meta[i][1]}">${meta[i][0]}</div><p style="margin:2px 0 0">${t}</p></div></div>`).join("")}</div></div>
 <div class="card"><div class="tb"><div class="lb">Telemetry explorer</div><div class="seg" id="tsel"></div></div><div id="tel" class="ech" style="height:280px"></div></div>`
  );
};
function ovInit() {
  const C1 = 2 * Math.PI * 118,
    C2 = 2 * Math.PI * 96,
    used = Math.min(1, (100 - sohNow) / (100 - P.E));
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      $("a1").style.strokeDashoffset = C1 * (1 - sohNow / 100);
      $("a2").style.strokeDashoffset = C2 * (1 - used);
    }),
  );
  const ex = xt(),
    obs = D.map((d) => [d.i, +d.soh.toFixed(2)]),
    fc = [];
  for (let i = N - 1; i < ex; i++) fc.push([i, +(F.b + F.s * i).toFixed(2)]);
  const o = eb(
    ex - 1,
    Math.floor(Math.min(P.E, sohNow) - 3),
    100,
    true,
    "{value}%",
  );
  o.series = [
    {
      name: "Observed (simulated)",
      type: "line",
      showSymbol: false,
      data: obs,
      lineStyle: { width: 2.2, color: "#7CF2BC" },
      areaStyle: window.echarts ? { color: area("#7CF2BC") } : null,
      markLine: {
        symbol: "none",
        silent: true,
        data: [
          {
            xAxis: N - 1,
            label: { formatter: "Forecast starts", color: "#8998AD" },
            lineStyle: { color: "#8998AD", type: "dotted" },
          },
          {
            yAxis: P.E,
            label: {
              formatter: "EOL " + P.E + "%",
              color: "#FF7185",
              position: "insideEndTop",
            },
            lineStyle: { color: "#FF7185", type: "dashed" },
          },
        ],
      },
    },
    {
      name: "Forecast (linear fit)",
      type: "line",
      showSymbol: false,
      data: fc,
      lineStyle: { width: 2, type: "dashed", color: "#54E7FF" },
    },
  ];
  const tc = ec(
    "tl",
    o,
    chart([{ d: col("soh"), c: "var(--gr)" }], { a: "SOH history" }),
  );
  $("rg").onclick = (e) => {
    const r = e.target.dataset.r;
    if (!r) return;
    $("rg")
      .querySelectorAll("button")
      .forEach((b) => b.classList.toggle("on", b === e.target));
    tc?.dispatchAction({
      type: "dataZoom",
      startValue: r == "all" ? 0 : N - 120,
      endValue: ex - 1,
    });
  };
  const M = {
    soh: ["SOH", "#7CF2BC", "%", 2],
    temp: ["Temperature", "#54E7FF", "°C", 2],
    volt: ["Voltage", "#FFC56E", "V", 3],
    cap: ["Capacity", "#8DAFFF", "Ah", 3],
  };
  let sel = "temp";
  const draw = () => {
    $("tsel").innerHTML = Object.entries(M)
      .map(
        ([k, m]) =>
          `<button data-m="${k}" class="${k == sel ? "on" : ""}">${m[0]}</button>`,
      )
      .join("");
    const m = M[sel],
      t = eb(
        N - 1,
        null,
        null,
        false,
        "{value}" + (m[2] == "%" ? "%" : ""),
        m[3],
      );
    t.series = [
      {
        name: m[0] + " (" + m[2] + ")",
        type: "line",
        showSymbol: false,
        data: D.map((d) => [d.i, d[sel]]),
        lineStyle: { width: 1.8, color: m[1] },
      },
    ];
    const mk = AN.filter((a) => a.k == sel);
    if (mk.length)
      t.series.push({
        name: "Flagged",
        type: "scatter",
        symbolSize: 9,
        itemStyle: { color: "#FF7185" },
        data: mk.map((a) => [a.c, a.v]),
      });
    ec("tel", t, chart([{ d: col(sel), c: m[1] }], { dp: m[3] }));
  };
  draw();
  $("tsel").onclick = (e) => {
    if (e.target.dataset.m) {
      sel = e.target.dataset.m;
      draw();
    }
  };
}
/* ---- Digital twin: isometric 3D-style pack (illustrative modules) ---- */
pages.digital = () =>
  head(
    "Battery Digital Twin",
    "A software representation driven by the selected cycle of the dataset. It is not connected to a vehicle.",
  ) +
  `<div class="tw"><div class="card"><div class="tb"><div class="seg" id="sg"><button data-m="soh" class="on">Health</button><button data-m="temp">Temperature</button></div><button class="btn o" id="rv">Reset view</button></div><div class="scene"><svg id="pack" viewBox="-200 -50 480 320" role="img" aria-label="Isometric battery pack of 24 illustrative modules"></svg></div><label>Cycle <span id="cv"></span></label><input type="range" id="cs" min="0" max="${N - 1}" value="${N - 1}"><div class="leg" id="lg"></div></div><div class="card" id="tinfo"></div></div><div class="note">The dataset holds pack-level measurements only. All 24 modules are drawn from the pack value; nothing here is a per-cell measurement. Select a module to lift it.</div>`;
function twInit() {
  let mode = "soh",
    pick = null;
  const cs = $("cs"),
    pk = $("pack"),
    a = 40,
    h = 26,
    Q = (x, y, z) =>
      ((x - y) * 0.866).toFixed(1) + "," + ((x + y) * 0.5 - z).toFixed(1);
  let s = `<polygon points="${Q(-10, -10, 0)} ${Q(290, -10, 0)} ${Q(290, 194, 0)} ${Q(-10, 194, 0)}" fill="#0f1621" stroke="#223149"/>`;
  for (let k = 0; k < 24; k++) {
    const x = (k % 6) * 48,
      y = Math.floor(k / 6) * 48;
    s += `<g class="mod" data-k="${k}" tabindex="0" role="button" aria-label="Module ${k + 1}"><polygon class="l" points="${Q(x, y + a, 0)} ${Q(x + a, y + a, 0)} ${Q(x + a, y + a, h)} ${Q(x, y + a, h)}"/><polygon class="r" points="${Q(x + a, y, 0)} ${Q(x + a, y + a, 0)} ${Q(x + a, y + a, h)} ${Q(x + a, y, h)}"/><polygon class="t" points="${Q(x, y, h)} ${Q(x + a, y, h)} ${Q(x + a, y + a, h)} ${Q(x, y + a, h)}"/></g>`;
  }
  pk.innerHTML = s;
  const draw = () => {
    const d = D[+cs.value];
    $("cv").textContent = d.i;
    const c =
      mode == "soh"
        ? hcol(d.soh)
        : d.temp < 30
          ? "var(--cy)"
          : d.temp < 40
            ? "var(--am)"
            : "var(--rd)";
    pk.querySelectorAll(".mod").forEach((g) => {
      g.querySelectorAll("polygon").forEach((p) => (p.style.fill = c));
      const on = +g.dataset.k === pick;
      g.style.transform = on ? "translateY(-9px)" : "none";
      g.querySelector(".t").style.stroke = on
        ? "#F5F7FC"
        : "rgba(255,255,255,.18)";
    });
    $("lg").innerHTML = (
      mode == "soh"
        ? [
            ["≥ 85% healthy", "var(--gr)"],
            ["80–85% caution", "var(--am)"],
            ["< 80% below threshold", "var(--rd)"],
          ]
        : [
            ["< 30 °C", "var(--cy)"],
            ["30–40 °C", "var(--am)"],
            ["> 40 °C", "var(--rd)"],
          ]
    )
      .map((x) => `<span><i style="background:${x[1]}"></i>${x[0]}</span>`)
      .join("");
    $("tinfo").innerHTML =
      `<div class="lb">Pack state at cycle ${d.i}</div><p style="margin:8px 0"><span class="tag s">Simulated</span> <span class="tag f">Pack-level</span></p><div class="stats2"><div><div class="lb">SOH</div><div class="big" style="color:${hcol(d.soh)}">${d.soh.toFixed(1)}<small>%</small></div></div><div><div class="lb">Capacity</div><div class="big">${d.cap.toFixed(3)}<small>Ah</small></div></div><div><div class="lb">Temperature</div><div class="big">${d.temp.toFixed(1)}<small>°C</small></div></div><div><div class="lb">Voltage</div><div class="big">${d.volt.toFixed(2)}<small>V</small></div></div></div><p class="mu">${pick == null ? "No module selected." : `Module ${pick + 1}: no cell-level measurement exists, so this shows the pack value (illustrative).`}</p>${chart([{ d: col("soh"), c: "var(--gr)", w: 1.5 }], { v: d.i, h: 150, a: "SOH with selected cycle" })}`;
  };
  draw();
  cs.oninput = draw;
  $("sg").onclick = (e) => {
    if (e.target.dataset.m) {
      mode = e.target.dataset.m;
      $("sg")
        .querySelectorAll("button")
        .forEach((b) => b.classList.toggle("on", b === e.target));
      draw();
    }
  };
  $("rv").onclick = () => {
    pick = null;
    cs.value = N - 1;
    draw();
    toast("View reset to the latest cycle");
  };
  pk.onclick = (e) => {
    const g = e.target.closest(".mod");
    if (g) {
      pick = +g.dataset.k;
      draw();
    }
  };
  pk.onkeydown = (e) => {
    if (e.key == "Enter") {
      const g = e.target.closest(".mod");
      if (g) {
        pick = +g.dataset.k;
        draw();
      }
    }
  };
}
/* ---- Simulator workspace: controls | prediction | results ---- */
pages.sim = () =>
  head(
    "What-If Simulator",
    "Compare operating scenarios against a 25 °C, 1C, 80% DoD baseline.",
  ) +
  `<div class="sg"><div class="card"><div class="lb">Scenario controls</div><div id="ctl"></div><div class="row"><button class="btn" id="sv">Save scenario</button><button class="btn o" id="rs">Reset</button></div><div id="sl" style="margin-top:14px"></div></div><div class="card"><div class="lb">Predicted behaviour</div><div id="schart" class="ech" style="height:400px"></div></div><div class="card" id="sres"></div></div><div class="note">Model: SOH(n) = SOH₀ − r·n·(1 + n/1500), r = recent fitted fade × e^(0.06·(T−25)) × (1 + 0.4·(C−1)) × (DoD/80)^0.9. The temperature, C-rate and DoD coefficients are assumed, not fitted. Outputs are simulated estimates.</div>`;
const SC2 = ["#FFC56E", "#FF7185", "#7CF2BC", "#B58CFF"];
function simDraw() {
  SL.forEach(
    ([k, , , , , u]) => ($("o" + k).textContent = P[k] + (u ? " " + u : "")),
  );
  const bp = { ...P, ...BASE },
    n = P.N,
    ser = (p) =>
      Array.from({ length: n + 1 }, (_, i) => [
        i,
        +Math.max(0, sohAt(p, i)).toFixed(2),
      ]);
  const cb = eolN(bp),
    cs = eolN(P),
    fin = sohAt(P, n),
    finB = sohAt(bp, n);
  const o = eb(
    n,
    Math.floor(Math.max(0, Math.min(fin, finB, P.E) - 3)),
    100,
    false,
    "{value}%",
  );
  o.series = [
    {
      name: "Baseline",
      type: "line",
      showSymbol: false,
      data: ser(bp),
      lineStyle: { width: 1.6, type: "dashed", color: "#8998AD" },
    },
    {
      name: "Current",
      type: "line",
      showSymbol: false,
      data: ser(P),
      lineStyle: { width: 2.6, color: "#54E7FF" },
      areaStyle: window.echarts ? { color: area("#54E7FF") } : null,
      markLine: {
        symbol: "none",
        silent: true,
        data: [
          {
            yAxis: P.E,
            label: {
              formatter: "EOL " + P.E + "%",
              color: "#FF7185",
              position: "insideEndTop",
            },
            lineStyle: { color: "#FF7185", type: "dashed" },
          },
        ],
      },
      markPoint: {
        data: [{ coord: [n, +fin.toFixed(2)], value: fin.toFixed(1) }],
        symbolSize: 44,
        itemStyle: { color: "#54E7FF" },
        label: { color: "#04141a", fontSize: 10, fontWeight: 700 },
      },
    },
    ...saved.map((s, i) => ({
      name: s.name,
      type: "line",
      showSymbol: false,
      data: ser(s.p),
      lineStyle: { width: 1.6, color: SC2[i] },
    })),
  ];
  ec(
    "schart",
    o,
    chart(
      [
        { d: ser(bp).map((v) => v[1]), c: "var(--mu)", dash: "5 4" },
        { d: ser(P).map((v) => v[1]), c: "var(--cy)" },
      ],
      { n: n + 1, max: 100 },
    ),
  );
  const dl = cs != null && cb != null ? cs - cb : null;
  $("sres").innerHTML =
    `<div class="lb">Estimated cycles to ${P.E}% SOH</div><div class="big xl" style="color:var(--cy)">${cs ?? ">5000"}</div><p style="font-weight:700;color:${dl > 0 ? "var(--gr)" : dl < 0 ? "var(--rd)" : "var(--mu)"}">${dl == null ? "–" : (dl > 0 ? "+" : "") + dl + " cycles vs baseline (" + ((dl / cb) * 100 > 0 ? "+" : "") + ((dl / cb) * 100).toFixed(0) + "%)"}</p><div class="stats2"><div><div class="lb">SOH after ${n}</div><b>${fin.toFixed(1)}%</b></div><div><div class="lb">Fade rate</div><b>${rate(P).toFixed(3)} %/cyc</b></div><div><div class="lb">Baseline cycles</div><b>${cb ?? ">5000"}</b></div><div><div class="lb">Baseline SOH</div><b>${finB.toFixed(1)}%</b></div></div><div class="lb">Assumptions</div><p class="mu" style="font-size:12.5px">Base fade ${fade.toFixed(3)} %/cycle fitted from the last 120 simulated cycles; scaling coefficients are assumed.</p><p style="margin-top:8px"><span class="tag s">Simulated estimate</span> <span class="tag">Uncertainty: not quantified</span></p>`;
  $("sl").innerHTML = saved.length
    ? `<div class="lb" style="margin-bottom:6px">Saved scenarios</div>` +
      saved
        .map(
          (s, i) =>
            `<div style="padding:8px 0;border-top:1px solid var(--bd)"><b style="color:${SCol[i]}">${s.name}</b> <span class="mu">${s.p.T}°C · ${s.p.C}C · ${s.p.D}%</span><div class="row" style="margin-top:6px"><button class="btn o" data-r="${i}">Rename</button><button class="btn o" data-u="${i}">Duplicate</button><button class="btn o" data-d="${i}">Delete</button></div></div>`,
        )
        .join("")
    : '<p class="mu" style="font-size:12.5px">Adjust the controls, then save a scenario to overlay it on the chart.</p>';
}
/* ---- Anomalies ---- */
pages.anom = () => {
  const hi = AN.filter((a) => a.sev == "h").length,
    L = [
      ["temp", "Temperature"],
      ["volt", "Voltage"],
      ["soh", "Capacity"],
    ];
  const X = (c) => 40 + (c / (N - 1)) * 670;
  const tl = `<svg viewBox="0 0 720 120" role="img" aria-label="Anomaly timeline">${L.map(
    ([k, l], i) => {
      const y = 24 + i * 30;
      return (
        `<text x="0" y="${y + 4}" fill="#8998AD" font-size="11">${l.slice(0, 5)}</text><line x1="40" x2="710" y1="${y}" y2="${y}" stroke="#1B2638"/>` +
        AN.filter((a) => a.k == k)
          .map(
            (a) =>
              `<circle cx="${X(a.c).toFixed(1)}" cy="${y}" r="5" fill="${a.sev == "h" ? "#FF7185" : "#FFC56E"}"><title>Cycle ${a.c}: ${a.t}</title></circle>`,
          )
          .join("")
      );
    },
  ).join(
    "",
  )}<text x="40" y="114" fill="#8998AD" font-size="11">cycle 0</text><text x="710" y="114" text-anchor="end" fill="#8998AD" font-size="11">cycle ${N - 1}</text></svg>`;
  return (
    head(
      "Anomaly Detection",
      "Robust z-score (median/MAD, threshold 3.5). Events are patterns to investigate, not confirmed faults.",
    ) +
    `<div class="k12"><div class="card s4"><div class="lb">Events flagged</div><div class="big xl" style="color:${AN.length ? "var(--am)" : "var(--gr)"}">${AN.length}</div><p class="mu"><b style="color:var(--rd)">${hi}</b> high · <b style="color:var(--am)">${AN.length - hi}</b> medium</p><p class="mu" style="font-size:12px">High = |z| above 6, medium = 3.5 to 6.</p></div><div class="card s8"><div class="lb">Timeline</div>${tl}</div></div>
 <div class="k12"><div class="card s6"><div class="lb">Temperature</div><div id="c1" class="ech" style="height:260px"></div></div><div class="card s6"><div class="lb">Voltage</div><div id="c2" class="ech" style="height:260px"></div></div></div>
 <div class="card wrap"><div class="lb" style="margin-bottom:8px">Detected events</div>${AN.length ? `<table><tr><th>Cycle</th><th>Type</th><th>Value</th><th>Expected range</th><th>Severity</th></tr>${AN.map((a) => `<tr><td>${a.c}</td><td>${a.t}</td><td>${a.v.toFixed(a.k == "volt" ? 3 : 2)} ${a.u}</td><td>${a.lo.toFixed(2)} to ${a.hi.toFixed(2)}</td><td class="sev ${a.sev}">${a.sev == "h" ? "High" : "Medium"}</td></tr>`).join("")}</table>` : '<p class="mu">No anomalies at this threshold. Lower the threshold or load more data to keep monitoring.</p>'}<p class="mu" style="margin-top:10px">Flagged when a value sits more than 3.5 robust standard deviations from the median.</p></div>`
  );
};
setTimeout(() => 0);
const _go = go;
go = function (k) {
  _go(k);
  if (k == "anom") {
    [
      ["c1", "temp", "#54E7FF", 2],
      ["c2", "volt", "#7CF2BC", 3],
    ].forEach(([id, key, c, dp]) => {
      const o = eb(N - 1, null, null, false, "{value}", dp);
      o.series = [
        {
          name: key,
          type: "line",
          showSymbol: false,
          data: D.map((d) => [d.i, d[key]]),
          lineStyle: { width: 1.6, color: c },
        },
        {
          name: "Flagged",
          type: "scatter",
          symbolSize: 9,
          itemStyle: { color: "#FF7185" },
          data: AN.filter((a) => a.k == key).map((a) => [a.c, a.v]),
        },
      ];
      ec(id, o, chart([{ d: col(key), c }], { dp }));
    });
  }
};
/* ---- Advisor ---- */
pages.advisor = () => {
  const b = eolN({ ...P, ...BASE }),
    R = [
      ["Cooler: 15 °C", { T: 15 }, "Lower temperature slows modelled fade"],
      ["Warmer: 35 °C", { T: 35 }, "Heat accelerates modelled fade"],
      [
        "Gentler charge: 0.5C",
        { C: 0.5 },
        "Slower charging reduces modelled stress",
      ],
      [
        "Fast charge: 2C",
        { C: 2 },
        "Faster charging increases modelled stress",
      ],
      [
        "Shallower cycles: 60% DoD",
        { D: 60 },
        "Less depth per cycle is gentler",
      ],
      [
        "Full-depth cycles: 100% DoD",
        { D: 100 },
        "Deeper cycles wear faster in the model",
      ],
    ];
  return (
    head(
      "Charging Advisor",
      "How each change would move cycles to end-of-life, under this simulator’s assumed coefficients.",
    ) +
    `<div class="card" style="margin-bottom:16px"><div class="lb">Baseline · 25 °C · 1C · 80% DoD from ${P.S}% SOH</div><div class="big xl" style="color:var(--cy)">${b ?? ">5000"}<small>cycles to ${P.E}% SOH</small></div></div><div class="card">${R.map(
      ([l, ch, w]) => {
        const n = eolN({ ...P, ...BASE, ...ch }),
          d = n && b ? ((n - b) / b) * 100 : 0,
          wd = Math.min(50, Math.abs(d) / 2);
        return `<div style="display:grid;grid-template-columns:minmax(150px,1fr) 2fr 100px;gap:16px;align-items:center;padding:12px 0;border-top:1px solid var(--bd)"><div><b>${l}</b><div class="mu" style="font-size:12px">${w}</div></div><div class="bar"><i style="left:${d >= 0 ? 50 : 50 - wd}%;width:${wd}%;background:${d >= 0 ? "var(--gr)" : "var(--rd)"}"></i></div><div style="text-align:right;font-variant-numeric:tabular-nums"><b>${n ?? ">5000"}</b> <span style="color:${d > 0 ? "var(--gr)" : "var(--rd)"}">${(d > 0 ? "+" : "") + d.toFixed(0)}%</span></div></div>`;
      },
    ).join(
      "",
    )}</div><div class="note">Modelled direction and relative size only, not guaranteed life gains. Coefficients are assumed, not fitted.</div>`
  );
};
/* ---- About ---- */
pages.about = () =>
  head("About", "Project information, method and limits.") +
  `<div class="k12"><div class="card s4"><div class="lb">Data</div><p style="margin-top:8px">${N} seeded synthetic cycles of a 2.0 Ah cell. Reproducible, not measured from any vehicle.</p></div><div class="card s4"><div class="lb">Method</div><p style="margin-top:8px">SOH = capacity ÷ ${NOM} Ah. RUL from a linear fit over the last 120 cycles, scored by a time-ordered backtest. Anomalies by median/MAD z-score. Simulator uses assumed coefficients.</p></div><div class="card s4"><div class="lb">Simulation vs a real EV</div><p style="margin-top:8px">This is a software simulation. It has no vehicle connection and does not replace a Battery Management System, diagnostics or warranty assessment.</p></div></div><div class="card"><div class="lb">Definitions</div><p style="margin-top:8px">SOC is the present charge level. SOH is condition relative to a reference. RUL estimates cycles before a chosen end-of-life criterion and is not a guaranteed replacement date.</p><p class="mu">Not included: CSV upload, Python backend, ML model comparison, PDF export.</p></div>`;
go(location.hash.slice(1) in pages ? location.hash.slice(1) : "overview");
