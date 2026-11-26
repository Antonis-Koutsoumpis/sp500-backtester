/* Index Backtester: web version of sp500_simulator.py (same calculations).
 * Data: data/index_prices.csv, data/metadata.json and data/indices.json, copied by
 * scripts/export_web.py in the daily GitHub Action. Charts: Plotly (vendor/).
 */
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const DAY = 86400000;
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const SCENARIO_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c"];
const PRESET_YEARS = [5, 10, 15, 20, 25, 30, 50];
const TOUCH = window.matchMedia("(pointer: coarse)").matches;

let INDICES = {}, CUR_SYM = {}, META = {}, ALL = {};   // ALL[index] = [{t, nominal, real}]
let AVAILABLE = [];

/* ---------------- formatting ---------------- */
const nf = (d) => new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const NF = [0, 1, 2, 3].map(nf);
const num = (x, d = 0) => NF[d].format(x);
const signed = (x, d) => (x >= 0 ? "+" : "") + num(x, d);           // like {x:+,.1f}
const pct = (x, d = 2, sign = false) => (sign ? signed(x * 100, d) : num(x * 100, d)) + "%";
const ymd = (t) => new Date(t).toISOString().slice(0, 10);
const monthStr = (t) => ymd(t).slice(0, 7);
const monthLabel = (m) => `${MONTH_NAMES[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}`;
const dateLabel = (t) => { const d = new Date(t); return `${String(d.getUTCDate()).padStart(2, "0")} ${MONTH_NAMES[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
const parseDate = (s) => { const m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(String(s).trim()); if (!m) return NaN; const t = Date.UTC(+m[1], +m[2] - 1, +m[3]); const d = new Date(t); return d.getUTCMonth() === +m[2] - 1 ? t : NaN; };
const monthStart = (t) => { const d = new Date(t); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1); };
const monthEnd = (m) => Date.UTC(+m.slice(0, 4), +m.slice(5, 7), 0);   // last day of month m ("YYYY-MM")
const addYears = (t, n) => { const d = new Date(t); return Date.UTC(d.getUTCFullYear() + n, d.getUTCMonth(), d.getUTCDate()); };
const yearsBetween = (a, b) => (b - a) / DAY / 365.25;
/** Python's {x:+,.4g} */
function fmtG(c) {
  if (c === 0) return "+0";
  const e = Math.floor(Math.log10(Math.abs(c)));
  let s;
  if (e < -4 || e >= 4) {
    const [m, ex] = c.toExponential(3).split("e");
    s = m.replace(/\.?0+$/, "") + "e" + (ex[0] === "-" ? "-" : "+") + ex.replace(/^[+-]/, "").padStart(2, "0");
  } else {
    s = new Intl.NumberFormat("en-US", { maximumFractionDigits: Math.max(0, 3 - e) }).format(c);
  }
  return (c >= 0 ? "+" : "") + s;
}

/* ---------------- state ---------------- */
const S = {
  index: "sp500", mode: "Nominal", scale: "Linear", trend: "None", degree: 2, scope: "Full history",
  winLen: null, winStart: null, winEnd: null,
  scenarios: [], cmpFixed: false, cmpRate: 10, cmpCash: false, showBears: false, showCauses: false,
};
let BEARS = [];   // S&P 500 bear markets, from data/bear_markets.json (bear_markets.py)
let DF = [], MONTHS = [], N = 0, MIN_DATE = 0, MAX_DATE = 0, VALUE = "nominal";

function scenarioDefaults(kind) {
  if (kind === "Lump sum") return { initial: 10000, contribution: 0, escalation: 0, frequency: "Yearly" };
  if (kind === "DCA") return { initial: 0, contribution: 5000, escalation: 0, frequency: "Yearly" };
  if (kind === "Escalated DCA") return { initial: 0, contribution: 5000, escalation: 2, frequency: "Yearly" };
  return { initial: 10000, contribution: 5000, escalation: 2, frequency: "Yearly" };
}
function newScenario(kind) {
  return { type: kind, useWindow: true, start: null, years: 10, ...scenarioDefaults(kind) };
}

/* ---------------- data ---------------- */
function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  const head = lines[0].split(",");
  const iI = head.indexOf("index"), iD = head.indexOf("date"), iN = head.indexOf("nominal"), iR = head.indexOf("inflation_adjusted");
  const out = {};
  for (let k = 1; k < lines.length; k++) {
    const c = lines[k].split(",");
    const id = c[iI];
    (out[id] ||= []).push({ t: parseDate(c[iD]), nominal: c[iN] === "" ? NaN : +c[iN], real: c[iR] === "" ? NaN : +c[iR] });
  }
  for (const id in out) out[id].sort((a, b) => a.t - b.t);
  return out;
}

/** Monthly rows for one index with a value for the chosen mode, plus monthly returns. */
function indexFrame(id, mode) {
  const key = mode === "Nominal" ? "nominal" : "real";
  const d = (ALL[id] || []).filter((r) => Number.isFinite(r[key]));
  return d.map((r, i) => {
    const p = d[i - 1];
    return {
      ...r,
      ret_nom: p ? r.nominal / p.nominal - 1 : NaN,
      ret_real: p ? r.real / p.real - 1 : NaN,
    };
  });
}

/* ---------------- time window ---------------- */
const presets = () => PRESET_YEARS.filter((n) => 12 * n <= N).map((n) => `${n} years`);
const windowOptions = () => [...presets(), "Full history", "Custom"];
const presetMonths = (c) => (presets().includes(c) ? 12 * parseInt(c, 10) : null);
function monthIndex(t) {
  const m = monthStr(t);
  if (m <= MONTHS[0]) return 0;
  if (m >= MONTHS[N - 1]) return N - 1;
  return MONTHS.findIndex((x) => x >= m);
}
function resolveWindow() {
  if (!windowOptions().includes(S.winLen)) S.winLen = presets().includes("20 years") ? "20 years" : "Full history";
  if (!MONTHS.includes(S.winStart) || !MONTHS.includes(S.winEnd)) {
    const L = presetMonths(S.winLen) || N;
    S.winStart = MONTHS[N - L]; S.winEnd = MONTHS[N - 1];
  }
  let si = MONTHS.indexOf(S.winStart), ei = MONTHS.indexOf(S.winEnd);
  const W = presetMonths(S.winLen);
  if (W) { si = Math.min(si, N - W); ei = si + W - 1; }
  else if (S.winLen === "Full history") { si = 0; ei = N - 1; }
  else if (ei <= si) { ei = Math.min(si + 1, N - 1); si = ei - 1; }
  S.winStart = MONTHS[si]; S.winEnd = MONTHS[ei];
  return [si, ei];
}
function shiftWindow(months) {
  const si = MONTHS.indexOf(S.winStart), ei = MONTHS.indexOf(S.winEnd);
  months = Math.max(-si, Math.min(months, N - 1 - ei));
  S.winStart = MONTHS[si + months]; S.winEnd = MONTHS[ei + months];
  update();
}
/** A drag across the main chart: zoom into that part of the window. */
function applyZoom(x0, x1) {
  let a = monthIndex(Math.min(x0, x1)), b = monthIndex(Math.max(x0, x1));
  if (b <= a) { b = Math.min(a + 1, N - 1); a = b - 1; }
  S.winLen = "Custom"; S.winStart = MONTHS[a]; S.winEnd = MONTHS[b];
  update();
}
/** A drag across the full-history strip (box from x0 to x1) or a click/tap (x0 only). */
function applySelection(x0, x1) {
  const si = MONTHS.indexOf(S.winStart), ei = MONTHS.indexOf(S.winEnd);
  if (x1 != null) {
    let a = monthIndex(Math.min(x0, x1)), b = monthIndex(Math.max(x0, x1));
    const W = presetMonths(S.winLen);
    if (W) { const len = W - 1; a = Math.min(a, N - 1 - len); S.winStart = MONTHS[a]; S.winEnd = MONTHS[a + len]; }
    else {
      if (b <= a) { b = Math.min(a + 1, N - 1); a = b - 1; }
      S.winLen = "Custom"; S.winStart = MONTHS[a]; S.winEnd = MONTHS[b];
    }
  } else {
    let a = monthIndex(x0);
    if (S.winLen === "Full history") { S.winLen = "Custom"; S.winStart = MONTHS[Math.min(a, N - 2)]; S.winEnd = MONTHS[N - 1]; }
    else {
      const len = presetMonths(S.winLen) ? presetMonths(S.winLen) - 1 : ei - si;
      a = Math.min(a, N - 1 - len); S.winStart = MONTHS[a]; S.winEnd = MONTHS[a + len];
    }
  }
  update();
}

/* ---------------- trend lines ---------------- */
function lstsq(X, y) {   // normal equations, small systems only
  const k = X[0].length, A = Array.from({ length: k }, () => new Array(k + 1).fill(0));
  for (let r = 0; r < X.length; r++) for (let i = 0; i < k; i++) { for (let j = 0; j < k; j++) A[i][j] += X[r][i] * X[r][j]; A[i][k] += X[r][i] * y[r]; }
  for (let c = 0; c < k; c++) {
    let p = c; for (let r = c + 1; r < k; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    [A[c], A[p]] = [A[p], A[c]];
    for (let r = 0; r < k; r++) if (r !== c) { const f = A[r][c] / A[c][c]; for (let j = c; j <= k; j++) A[r][j] -= f * A[c][j]; }
  }
  return A.map((row, i) => row[k] / row[i]);
}
const binom = (n, k) => { let r = 1; for (let i = 1; i <= k; i++) r = (r * (n - i + 1)) / i; return r; };
function fitTrend(ts, ys, kind, degree) {
  const t = ts.map((x) => yearsBetween(ts[0], x));
  let fitted, formula;
  if (kind === "Linear") {
    const [a, b] = lstsq(t.map((x) => [1, x]), ys);
    fitted = t.map((x) => a + b * x);
    formula = `y = ${num(a, 2)} + ${num(b, 2)}·t`;
  } else if (kind === "Polynomial") {
    const lo = Math.min(...t), hi = Math.max(...t), c = (lo + hi) / 2, h = (hi - lo) / 2 || 1;
    const x = t.map((v) => (v - c) / h);
    const a = lstsq(x.map((v) => Array.from({ length: degree + 1 }, (_, k) => v ** k)), ys);
    const coef = new Array(degree + 1).fill(0);   // convert to powers of t
    a.forEach((ak, k) => { for (let j = 0; j <= k; j++) coef[j] += ak * binom(k, j) * (-c) ** (k - j) / h ** k; });
    fitted = t.map((v) => coef.reduce((s, ck, k) => s + ck * v ** k, 0));
    formula = "y = " + coef.map((ck, k) => fmtG(ck) + (k === 0 ? "" : k === 1 ? "·t" : `·t^${k}`)).join(" ").replace(/^\+/, "");
  } else if (kind === "Logarithmic") {
    const tl = t.map((v) => v + 1 / 12);
    const [a, b] = lstsq(tl.map((v) => [1, Math.log(v)]), ys);
    fitted = tl.map((v) => a + b * Math.log(v));
    formula = `y = ${num(a, 2)} + ${num(b, 2)}·ln(t + 1/12)`;
  } else {
    const idx = ys.map((v, i) => i).filter((i) => ys[i] > 0);
    const [lnA, b] = lstsq(idx.map((i) => [1, t[i]]), idx.map((i) => Math.log(ys[i])));
    const a = Math.exp(lnA);
    fitted = t.map((v) => a * Math.exp(b * v));
    formula = `y = ${num(a, 2)}·e^(${b.toFixed(4)}·t)  →  about ${num((Math.exp(b) - 1) * 100, 2)}% a year`;
  }
  const mean = ys.reduce((s, v) => s + v, 0) / ys.length;
  const ssRes = ys.reduce((s, v, i) => s + (v - fitted[i]) ** 2, 0), ssTot = ys.reduce((s, v) => s + (v - mean) ** 2, 0);
  return { fitted, formula, r2: ssTot > 0 ? 1 - ssRes / ssTot : NaN };
}

/* ---------------- IRR ---------------- */
function irrMonthly(cf, tol = 1e-7, maxIter = 200) {
  const npv = (r) => cf.reduce((s, c, t) => s + c / (1 + r) ** t, 0);
  let lo = -0.2, hi = 0.2;
  if (npv(lo) * npv(hi) > 0) return null;
  for (let i = 0; i < maxIter; i++) {
    const mid = (lo + hi) / 2, v = npv(mid);
    if (Math.abs(v) < tol) return mid;
    if (npv(lo) * v < 0) hi = mid; else lo = mid;
  }
  return (lo + hi) / 2;
}
const irrAnnual = (cf) => { const m = irrMonthly(cf); return m == null ? null : (1 + m) ** 12 - 1; };
function xirr(dates, flows) {
  const yrs = dates.map((d) => yearsBetween(dates[0], d));
  const npv = (r) => flows.reduce((s, f, i) => s + f / (1 + r) ** yrs[i], 0);
  let lo = -0.95, hi = 2.0;
  const a = npv(lo), b = npv(hi);
  if (!Number.isFinite(a) || !Number.isFinite(b) || a * b > 0) return null;
  for (let i = 0; i < 200; i++) { const mid = (lo + hi) / 2; if (npv(lo) * npv(mid) <= 0) hi = mid; else lo = mid; }
  return Math.round(((lo + hi) / 2) * 1e6) / 1e6 + 0;
}

/* ---------------- simulation (same as simulate() in sp500_simulator.py) ---------------- */
function simulate(df, startT, years, initial, contribution, escalation, frequency, mode, endT) {
  const retKey = mode === "Nominal" ? "ret_nom" : "ret_real";
  const start = monthStart(startT);
  const endTarget = endT == null ? addYears(start, years) - DAY : endT;
  const end = Math.min(endTarget, MAX_DATE);
  const win = df.filter((r) => r.t >= start && r.t <= end);
  if (!win.length) return null;
  const prev = df.filter((r) => r.t < start);
  const hasBase = prev.length > 0 && Number.isFinite(win[0][retKey]);
  const baseDate = hasBase ? prev[prev.length - 1].t : win[0].t;

  let portfolio = 0, invested = 0, peak = 0;
  const rows = [], cashflows = [];
  const d0 = new Date(win[0].t), startYear = d0.getUTCFullYear(), startMonth = d0.getUTCMonth() + 1;
  let months;
  if (frequency === "Yearly") months = new Set([startMonth]);
  else if (frequency === "Quarterly") months = new Set([0, 1, 2, 3].map((k) => ((startMonth - 1 + 3 * k) % 12) + 1));
  else months = new Set([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);

  win.forEach((row, i) => {
    let contrib = 0;
    const d = new Date(row.t), y = d.getUTCFullYear(), m = d.getUTCMonth() + 1;
    if (i === 0) contrib += initial;
    if (contribution > 0) {
      const escalated = contribution * (1 + escalation) ** (y - startYear);
      if (frequency === "Yearly") {
        if (m === startMonth && (i > 0 || initial === 0)) contrib += escalated;
        else if (i === 0) contrib += escalated;
      } else if (months.has(m) && !(i === 0 && initial > 0)) contrib += escalated;
    }
    portfolio += contrib; invested += contrib;
    cashflows.push(-contrib);
    if (i === 0 && hasBase) {
      peak = portfolio;
      rows.push({ t: baseDate, contribution: contrib, portfolio, invested, drawdown: 0 });
      contrib = 0;
    }
    if (i > 0 || hasBase) { const r = row[retKey]; if (Number.isFinite(r)) portfolio *= 1 + r; }
    peak = Math.max(peak, portfolio);
    rows.push({ t: row.t, contribution: contrib, portfolio, invested, drawdown: peak > 0 ? portfolio / peak - 1 : 0 });
  });
  const final = rows[rows.length - 1].portfolio;
  if (hasBase) cashflows.push(final); else cashflows[cashflows.length - 1] += final;
  const yrs = yearsBetween(rows[0].t, rows[rows.length - 1].t);
  const cagr = initial > 0 && contribution === 0 ? (yrs > 0 ? (final / initial) ** (1 / yrs) - 1 : 0) : null;
  let irr = null;
  try { irr = contribution > 0 || initial > 0 ? irrAnnual(cashflows) : null; } catch (e) { irr = null; }
  return {
    rows,
    m: {
      start, end: rows[rows.length - 1].t, years: yrs, invested, final,
      net_gain: final - invested, net_gain_pct: invested > 0 ? (final - invested) / invested : 0,
      cagr, irr, max_dd: Math.min(...rows.map((r) => r.drawdown)),
    },
  };
}

function lineMetrics(rows, values, lump) {
  const invested = rows.reduce((s, r) => s + r.contribution, 0);
  const final = values[values.length - 1];
  const yrs = yearsBetween(rows[0].t, rows[rows.length - 1].t);
  const flows = rows.map((r) => -r.contribution).concat(final);
  const dates = [rows[0].t, ...rows.slice(0, -1).map((r) => r.t), rows[rows.length - 1].t];
  let peak = -Infinity, dd = 0;
  for (const v of values) { peak = Math.max(peak, v); dd = Math.min(dd, peak > 0 ? v / peak - 1 : 0); }
  return {
    invested, final, net_gain: final - invested, net_gain_pct: invested > 0 ? final / invested - 1 : 0,
    cagr: lump && invested > 0 && yrs > 0 && final > 0 ? (final / invested) ** (1 / yrs) - 1 : null,
    irr: lump ? null : xirr(dates, flows), max_dd: dd,
  };
}
function fixedReturnPath(rows, rate) {
  let v = 0;
  return rows.map((r, i) => (v = i === 0 ? r.contribution : (v + r.contribution) * (1 + rate) ** ((r.t - rows[i - 1].t) / DAY / 365.25)));
}
function cashRealPath(rows, inflation) {
  let v = 0;
  return rows.map((r, i) => {
    if (i === 0) return (v = r.contribution);
    const inf = inflation.get(r.t);
    return (v = (v + r.contribution) / (1 + (Number.isFinite(inf) ? inf : 0)));
  });
}
function yearlyReturns(rows) {
  const groups = new Map();
  for (const r of rows) { const y = new Date(r.t).getUTCFullYear(); if (!groups.has(y)) groups.set(y, []); groups.get(y).push(r); }
  const out = []; let prev = null;
  for (const [y, g] of groups) {
    const last = g[g.length - 1].portfolio;
    if (prev == null) {
      if (g.length === 1 && rows.length > 1) { prev = last; continue; }
      prev = g[0].portfolio;
    }
    out.push({ year: y, ret: prev > 0 ? last / prev - 1 : 0 });
    prev = last;
  }
  return out;
}

/* ---------------- Plotly helpers ---------------- */
function themeLayout(extra) {
  const cs = getComputedStyle(document.documentElement);
  const text = cs.getPropertyValue("--text").trim(), line = cs.getPropertyValue("--line").trim();
  return {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: text, family: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif", size: 12 },
    xaxis: { gridcolor: line, zerolinecolor: line, ...(extra.xaxis || {}) },
    yaxis: { gridcolor: line, zerolinecolor: line, ...(extra.yaxis || {}) },
    margin: { t: 10, b: 40, l: 60, r: 15 },
    ...Object.fromEntries(Object.entries(extra).filter(([k]) => k !== "xaxis" && k !== "yaxis")),
  };
}
const PLOT_CONFIG = { displaylogo: false, responsive: true, displayModeBar: !TOUCH, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"] };
const isoX = (t) => ymd(t);

/* ---------------- S&P 500 bear markets (same as add_bear_markets in bear_markets.py) ---------------- */
const BEAR_FILL = "rgba(128, 128, 128, 0.18)";
const bearDate = (t) => { const d = new Date(t); return `${String(d.getUTCDate()).padStart(2, "0")} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
const bearsIn = (x0, x1) => BEARS.filter((b) => Date.parse(b.trough) >= x0 && Date.parse(b.peak) <= x1);
/** Breaks text into lines of about n characters (<br>), so a hover box fits on a phone. */
const wrapText = (text, n) => text.split(" ").reduce((lines, w) => {
  const last = lines[lines.length - 1];
  if (last && (last + " " + w).length <= n) lines[lines.length - 1] = last + " " + w; else lines.push(w);
  return lines;
}, []).join("<br>");
/** Plotly shapes (grey areas) and, with causes, labels for the bear markets between x0 and x1 (ms). */
function bearLayout(x0, x1, causes, widthPx = 0) {
  const shapes = [], annotations = [];
  // labels closer than 13 px apart would overlap: keep the first (the list under the chart has them all)
  const minGap = widthPx ? 13 * (x1 - x0) / widthPx : 0;
  let lastLabel = -Infinity;
  for (const b of bearsIn(x0, x1)) {
    const p = Date.parse(b.peak), t = Date.parse(b.trough);
    shapes.push({ type: "rect", xref: "x", yref: "paper", x0: b.peak, x1: b.trough, y0: 0, y1: 1, fillcolor: BEAR_FILL, line: { width: 0 }, layer: "below" });
    if (causes) {
      const a = Math.max(p, x0), z = Math.min(t, x1), mid = a + (z - a) / 2;
      if (mid - lastLabel < minGap) continue;
      lastLabel = mid;
      annotations.push({ x: ymd(mid), xref: "x", y: 1, yref: "paper", yanchor: "top", text: esc(b.label), textangle: -90, showarrow: false,
        font: { size: 10, color: "rgba(128, 128, 128, 0.95)" },
        hovertext: `<b>${esc(b.label)}</b><br>${bearDate(p)} – ${bearDate(t)}: ${b.decline.toFixed(1)}%<br>${wrapText(esc(b.cause), 45)}` });
    }
  }
  return { shapes, annotations };
}
function bearList(x0, x1) {
  const list = bearsIn(x0, x1);
  return `<details class="panel"><summary>What drove the S&amp;P 500 bear markets in this window (${list.length})</summary>
    ${list.length ? `<ul class="prose">${list.map((b) => `<li><b>${esc(b.label)}</b> · ${bearDate(Date.parse(b.peak))} – ${bearDate(Date.parse(b.trough))} · S&amp;P 500 ${b.decline.toFixed(1)}%<br>${esc(b.cause)}</li>`).join("")}</ul>` : `<p class="caption">No S&amp;P 500 bear market in this window.</p>`}
    <p class="caption">Peak-to-low dates and falls of the S&amp;P 500 (daily closes; Yardeni Research). The chart uses month-end values, so its fall can look smaller.</p></details>`;
}

/* ---------------- rendering ---------------- */
let histHandlersBound = false;
function renderHistory(si, ei) {
  const IDX = INDICES[S.index];
  $("#histTitle").textContent = `Historical chart — ${IDX.name}`;
  // window length chips
  const box = $("#winLen"); box.innerHTML = "";
  for (const o of windowOptions()) {
    const b = document.createElement("button"); b.type = "button"; b.className = "chip"; b.textContent = o;
    b.setAttribute("aria-pressed", o === S.winLen);
    b.onclick = () => {
      // from the full history to a fixed length: show the most recent window
      if (S.winLen === "Full history" && presetMonths(o)) S.winStart = MONTHS[N - presetMonths(o)];
      S.winLen = o; update();
    };
    box.appendChild(b);
  }
  // slider(s)
  const W = presetMonths(S.winLen), sb = $("#winSliderBox");
  if (W) {
    sb.innerHTML = `<label>Window start: <b>${monthLabel(S.winStart)}</b></label><input type="range" min="0" max="${N - W}" value="${si}" step="1" aria-label="Window start">`;
    const r = sb.querySelector("input");
    r.oninput = () => { sb.querySelector("b").textContent = monthLabel(MONTHS[+r.value]); };
    r.onchange = () => { S.winStart = MONTHS[+r.value]; update(); };
  } else if (S.winLen === "Custom") {
    sb.innerHTML = `<div class="month-row"><div><label>From: <b>${monthLabel(S.winStart)}</b></label><input type="range" min="0" max="${N - 1}" value="${si}" aria-label="Window start"></div>
      <div><label>To: <b>${monthLabel(S.winEnd)}</b></label><input type="range" min="0" max="${N - 1}" value="${ei}" aria-label="Window end"></div></div>`;
    const [a, b] = sb.querySelectorAll("input"), [la, lb] = sb.querySelectorAll("b");
    a.oninput = () => { la.textContent = monthLabel(MONTHS[+a.value]); };
    b.oninput = () => { lb.textContent = monthLabel(MONTHS[+b.value]); };
    const apply = () => {
      let x = +a.value, y = +b.value; if (x > y) [x, y] = [y, x];
      if (x === y) { if (y < N - 1) y++; else x--; }
      S.winStart = MONTHS[x]; S.winEnd = MONTHS[y]; update();
    };
    a.onchange = apply; b.onchange = apply;
  } else {
    sb.innerHTML = `<p class="caption">Showing the full history. Choose a window length${TOUCH ? "" : ", or drag across the chart to zoom into a period"}.</p>`;
  }
  const full = S.winLen === "Full history";
  $("#back1").hidden = $("#fwd1").hidden = full;
  $("#back1").disabled = si === 0; $("#fwd1").disabled = ei === N - 1;

  // chart
  // The main chart shows only the selected window (from the close of the
  // month before it, where the scenarios start investing).
  const base = DF.slice(Math.max(si - 1, 0), ei + 1);
  const bx = base.map((r) => isoX(r.t));
  const traces = [
    { x: bx, y: base.map((r) => r[VALUE]), name: IDX.name, mode: "lines", line: { color: "#1f77b4", width: 2 }, hovertemplate: "%{x|%b %Y}: %{y:,.2f}<extra></extra>" },
  ];
  let trendInfo = null;
  if (S.trend !== "None") {
    const fit = S.scope === "Full history" ? DF : base;
    if (fit.length > Math.max(3, S.degree + 1)) {
      const r = fitTrend(fit.map((d) => d.t), fit.map((d) => d[VALUE]), S.trend, S.degree);
      const name = S.trend === "Polynomial" ? `Polynomial trend (degree ${S.degree})` : `${S.trend} trend`;
      // fitted on `fit`, drawn only over the window
      const k0 = fit.findIndex((d) => d.t >= base[0].t);
      traces.push({ x: fit.slice(k0).map((d) => isoX(d.t)), y: r.fitted.slice(k0), name, mode: "lines", line: { color: "#d62728", width: 2, dash: "dash" }, hovertemplate: `${name}: %{y:,.2f}<extra></extra>` });
      trendInfo = { name, ...r, t0: fit[0].t };
    }
  }
  const bears = S.showBears ? bearLayout(base[0].t, base[base.length - 1].t, S.showCauses, $("#histChart").clientWidth * 0.85) : { shapes: [], annotations: [] };
  const layout = themeLayout({
    dragmode: TOUCH ? false : "select", selectdirection: "h", hovermode: "x", showlegend: false, ...bears,
    yaxis: { title: { text: S.mode === "Nominal" ? `Index level (${IDX.currency})` : `Index level (today's ${IDX.currency})` }, type: S.scale === "Log" ? "log" : "linear" },
    xaxis: { type: "date", range: [bx[0], bx[bx.length - 1]] },
  });
  Plotly.react("histChart", traces, layout, { ...PLOT_CONFIG, modeBarButtonsToRemove: ["lasso2d", "autoScale2d"] });

  // Navigator: the full history with the window highlighted.
  $("#navBox").hidden = full;
  if (!full) {
    $("#navCaption").textContent = `Full history — ${TOUCH ? "tap" : "drag or click"} here to move the window.`;
    const nav = [
      { x: DF.map((r) => isoX(r.t)), y: DF.map((r) => r[VALUE]), mode: "lines", line: { color: "rgba(120,130,145,0.9)", width: 1.2 }, hovertemplate: "%{x|%b %Y}<extra></extra>" },
      { x: bx, y: base.map((r) => r[VALUE]), mode: "lines", line: { color: "#1f77b4", width: 2 }, hoverinfo: "skip" },
    ];
    const navLayout = themeLayout({
      dragmode: TOUCH ? false : "select", selectdirection: "h", hovermode: "x", showlegend: false,
      margin: { t: 4, b: 22, l: 10, r: 10 },
      yaxis: { visible: false, type: S.scale === "Log" ? "log" : "linear" },
      xaxis: { type: "date", showgrid: false, range: [isoX(DF[0].t), isoX(DF[N - 1].t)] },
      shapes: [...(S.showBears ? bearLayout(DF[0].t, DF[N - 1].t, false).shapes : []),
        { type: "rect", xref: "x", yref: "paper", x0: isoX(monthStart(Date.UTC(+S.winStart.slice(0, 4), +S.winStart.slice(5) - 1, 1))), x1: isoX(monthEnd(S.winEnd)), y0: 0, y1: 1, fillcolor: "#1f77b4", opacity: 0.15, line: { width: 0 }, layer: "below" }],
    });
    Plotly.react("navChart", nav, navLayout, { ...PLOT_CONFIG, displayModeBar: false });
  }
  if (!histHandlersBound) {
    const el = $("#histChart"), nv = $("#navChart");
    el.on("plotly_selected", (ev) => { if (ev && ev.range && ev.range.x) applyZoom(Date.parse(ev.range.x[0]), Date.parse(ev.range.x[1])); });
    nv.on("plotly_selected", (ev) => { if (ev && ev.range && ev.range.x) applySelection(Date.parse(ev.range.x[0]), Date.parse(ev.range.x[1])); });
    nv.on("plotly_click", (ev) => { if (ev && ev.points && ev.points[0]) applySelection(Date.parse(ev.points[0].x)); });
    histHandlersBound = true;
  }
  $("#trendInfo").innerHTML = trendInfo
    ? `<span style="color:#d62728"><b>- - -</b></span> <b>${esc(trendInfo.name)}</b> (${S.scope.toLowerCase()}): <code>${esc(trendInfo.formula)}</code>, with t = years since ${monthLabel(monthStr(trendInfo.t0))} · R² = ${trendInfo.r2.toFixed(3)} (1 = perfect fit)` : "";
  $("#bearInfo").innerHTML = S.showBears && S.showCauses ? bearList(base[0].t, base[base.length - 1].t) : "";

  // window numbers
  const v0 = base[0][VALUE], v1 = base[base.length - 1][VALUE];
  const wy = yearsBetween(base[0].t, base[base.length - 1].t);
  const growth = v1 / v0 - 1, cagr = wy > 0 ? (v1 / v0) ** (1 / wy) - 1 : null;
  $("#winLabel").textContent = `${monthLabel(S.winStart)} – ${monthLabel(S.winEnd)} (${num(wy, 1)} years)`;
  $("#winTiles").innerHTML = tile("Index level", `${num(v0)} → ${num(v1)}`)
    + tile("Index total growth", pct(growth, 1, true), "Change in the index level over the window (price only, no dividends).")
    + tile("Index CAGR", cagr != null ? pct(cagr, 2) : "—", "Average yearly growth of the index over the window.");
  const how = TOUCH ? "tap" : "drag on";
  $("#winTip").textContent = "Tip: " + (W
    ? `${how} the full-history strip where the window should start: it keeps its length.${TOUCH ? "" : " Drag across the main chart to zoom into part of the window."}`
    : full ? (TOUCH ? "choose a window length to look at a period." : "drag across the chart to zoom into a period.")
    : `${TOUCH ? "tap the full-history strip to move the window, or use the sliders." : "drag across the full-history strip, or the main chart, to choose the start and end you want."}`) + " The scenarios below are calculated over this window.";
}

function tile(label, value, help) {
  return `<div class="tile"><div class="lab">${help ? `<abbr title="${esc(help)}">${esc(label)}</abbr>` : esc(label)}</div><div class="val">${esc(value)}</div></div>`;
}

function renderIndexInfo() {
  const IDX = INDICES[S.index], m = (META.indices || {})[S.index] || {};
  const facts = [`<b>Region:</b> ${esc(IDX.region)}`, `<b>Currency:</b> ${esc(IDX.currency)}`,
    `<b>Data:</b> ${dateLabel(MIN_DATE)} – ${dateLabel(MAX_DATE)}`, `<b>Source:</b> Yahoo Finance <code>${esc(m.ticker || IDX.tickers[0])}</code>`];
  if (S.mode === "Inflation-adjusted" && m.cpi) facts.push(`<b>Inflation:</b> ${esc(m.cpi)} (published up to ${esc(m.cpi_last_month || "?")}; later months use the last available figure)`);
  $("#indexInfo").innerHTML = `<h3>${esc(IDX.name)}</h3><p class="prose">${esc(IDX.description)}</p><p class="caption">${facts.join("  ·  ")}</p>`;
}

function renderGuide() {
  const rows = AVAILABLE.map((k) => {
    const m = (META.indices || {})[k] || {}, I = INDICES[k];
    return `<tr><td>${esc(I.name)}</td><td>${esc(I.short)}</td><td>${esc(I.region)}</td><td>${esc(I.currency)}</td><td>${esc(m.first_date || "—")}</td><td>${esc(m.ticker || I.tickers[0])}</td></tr>`;
  });
  $("#guide").innerHTML = `<tr><th>Index</th><th>What it is</th><th>Region</th><th>Currency</th><th>Data from</th><th>Source</th></tr>${rows.join("")}`;
  $("#updated").textContent = META.updated_utc ? `Data last updated: ${META.updated_utc}.` : "";
}

const CAGR_HELP = "CAGR (Compound Annual Growth Rate): the average yearly growth of a single amount invested once at the start: (final ÷ invested)^(1 ÷ years) − 1. For a lump sum, CAGR and IRR are the same number.";
const IRR_HELP = "IRR (Internal Rate of Return): the average yearly return on your money when you invest at different moments; each deposit counts only for the time it was actually invested. Compare with the index CAGR under the historical chart: above it, your deposit timing helped; below it, the timing hurt.";

function metricTiles(m, cur) {
  return `<div class="tiles">${tile("Invested", `${cur}${num(m.invested)}`)}${tile("Total growth", pct(m.net_gain_pct, 1, true), "Final value compared with everything invested: final ÷ invested − 1.")}${
    m.cagr != null ? tile("CAGR", pct(m.cagr, 2), CAGR_HELP) : tile("IRR", m.irr != null ? pct(m.irr, 2) : "—", IRR_HELP)}${tile("Final value", `${cur}${num(m.final)}`)}</div>`;
}

function runScenarios() {
  const warnings = [], runs = [];
  const WIN_START = Date.UTC(+S.winStart.slice(0, 4), +S.winStart.slice(5) - 1, 1), WIN_END = monthEnd(S.winEnd);
  S.scenarios.forEach((sc, idx) => {
    sc._err = "";
    if (!sc.initial && !sc.contribution) { warnings.push(`Scenario ${idx + 1} has no contributions — skipped.`); return; }
    let start;
    if (sc.useWindow) start = WIN_START;
    else {
      start = parseDate(sc.start);
      const def = Math.max(Date.UTC(1999, 0, 1), MIN_DATE);
      if (!Number.isFinite(start)) { sc._err = "Invalid date format. Use YYYY-MM-DD."; start = def; }
      if (start < MIN_DATE) { sc._err = `Start before ${ymd(MIN_DATE)}: clamped.`; start = MIN_DATE; }
      if (start > MAX_DATE) { sc._err = `Start after ${ymd(MAX_DATE)}: clamped.`; start = MAX_DATE; }
      if (sc._err) warnings.push(`Scenario ${idx + 1}: ${sc._err}`);
    }
    const res = simulate(DF, start, sc.years, sc.initial, sc.contribution, sc.escalation / 100, sc.frequency, S.mode, sc.useWindow ? WIN_END : null);
    if (!res) { warnings.push(`Scenario ${idx + 1}: no data in chosen window — skipped.`); return; }
    const requestedEnd = addYears(monthStart(start), sc.years) - DAY;
    if (!sc.useWindow && requestedEnd > MAX_DATE) warnings.push(`Scenario ${idx + 1}: requested end ${monthLabel(monthStr(requestedEnd))} beyond available data — capped at ${monthLabel(monthStr(MAX_DATE))}.`);
    runs.push({ name: `Scenario ${idx + 1} (${sc.type})`, ...res, params: sc });
  });
  return { runs, warnings };
}

function renderResults() {
  const IDX = INDICES[S.index], cur = CUR_SYM[IDX.currency] || "";
  const meta = (META.indices || {})[S.index] || {};
  const cpiLabel = meta.cpi || "the inflation of the index's currency area";
  $("#cashHint").textContent = `The same money kept as cash, earning no interest. Inflation (${cpiLabel}) eats away its purchasing power. Inflation-adjusted mode: the line shrinks; Nominal mode: it stays flat and the purchasing power lost is shown below the numbers.`;
  const { runs, warnings } = runScenarios();
  document.querySelectorAll(".scen .err").forEach((el) => { el.textContent = S.scenarios[+el.dataset.i]?._err || ""; });
  $("#warnings").innerHTML = warnings.map((w) => `<div class="notice warn-box">${esc(w)}</div>`).join("");
  $("#results").hidden = !runs.length;
  if (!runs.length) return;

  const inflation = new Map(DF.map((r) => [r.t, (1 + r.ret_nom) / (1 + r.ret_real) - 1]));
  const rate = S.cmpRate / 100;
  for (const r of runs) {
    const lump = r.params.contribution === 0;
    if (!lump) r.m.irr = lineMetrics(r.rows, r.rows.map((x) => x.portfolio), false).irr;
    r.comparisons = [];
    if (S.cmpFixed) {
      const vals = fixedReturnPath(r.rows, rate);
      r.comparisons.push({ key: "fixed", label: `Fixed ${signed(rate * 100, 1)}% a year`, values: vals, m: lineMetrics(r.rows, vals, lump) });
    }
    if (S.cmpCash) {
      const realVals = cashRealPath(r.rows, inflation);
      let cum = 0;
      const vals = S.mode === "Nominal" ? r.rows.map((x) => (cum += x.contribution)) : realVals;
      const m = lineMetrics(r.rows, vals, lump);
      m.power_lost = m.invested > 0 ? realVals[realVals.length - 1] / m.invested - 1 : 0;
      r.comparisons.push({ key: "cash", label: "Cash, 0% interest", values: vals, m });
    }
  }

  // metrics
  let h = "";
  for (const r of runs) {
    h += `<div class="scen-title">${esc(r.name)} · ${monthLabel(monthStr(r.m.start))} – ${monthLabel(monthStr(r.m.end))}</div>${metricTiles(r.m, cur)}`;
    for (const c of r.comparisons) {
      h += `<div class="cmp-title">↳ ${esc(c.label)} — same deposits</div><div class="cmp-tiles">${metricTiles(c.m, cur)}</div>`;
      if (c.key === "cash" && S.mode === "Nominal")
        h += `<p class="caption cmp-tiles">Purchasing power: the cash buys <b>${pct(c.m.power_lost, 1, true)}</b> compared with when it was saved (${esc(cpiLabel)}). Switch to <i>Inflation-adjusted</i> to see the shrinking value on the chart.</p>`;
    }
  }
  $("#metrics").innerHTML = h;

  // equity chart
  const narrow = window.innerWidth < 700;
  const legend = narrow ? { orientation: "h", yanchor: "top", y: -0.22, x: 0 } : { orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "right", x: 1 };
  const eq = [];
  runs.forEach((r, i) => {
    const color = SCENARIO_COLORS[i % 3], x = r.rows.map((p) => yearsBetween(r.rows[0].t, p.t));
    eq.push({ x, y: r.rows.map((p) => p.portfolio), mode: "lines", name: r.name, line: { color, width: 2.5 }, hovertemplate: `${cur}%{y:,.0f}` });
    for (const c of r.comparisons) eq.push({ x, y: c.values, mode: "lines", name: `${r.name} — ${c.label}`, line: { color, width: 1.8, dash: c.key === "fixed" ? "dash" : "dot" }, hovertemplate: `${cur}%{y:,.0f}` });
  });
  Plotly.react("eqChart", eq, themeLayout({
    xaxis: { title: { text: "Years since start" } }, yaxis: { title: { text: `Portfolio value (${IDX.currency})` }, type: S.scale === "Log" ? "log" : "linear" },
    hovermode: "x unified", legend, margin: { t: narrow ? 10 : 40, b: 45, l: 70, r: 15 },
  }), PLOT_CONFIG);
  $("#eqNote").textContent = runs.some((r) => r.comparisons.length) ? "Solid line = invested in the index · dashed = fixed annual return · dotted = cash savings." : "";

  // yearly returns
  const yr = runs.map((r) => {
    const y = yearlyReturns(r.rows);
    return { type: "bar", x: y.map((v) => v.year), y: y.map((v) => v.ret * 100), name: r.name,
      marker: { color: y.map((v) => (v.ret >= 0 ? "rgba(46,160,67,0.75)" : "rgba(220,53,69,0.75)")) },
      hovertemplate: "Year %{x}<br>Return: %{y:.1f}%<extra></extra>" };
  });
  Plotly.react("yrChart", yr, themeLayout({
    xaxis: { title: { text: "Calendar year" } }, yaxis: { title: { text: "Yearly return (%)" } }, barmode: "group", hovermode: "x unified", legend,
    margin: { t: narrow ? 10 : 40, b: 45, l: 60, r: 15 },
    shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0, line: { width: 1, color: getComputedStyle(document.documentElement).getPropertyValue("--text") } }],
  }), PLOT_CONFIG);

  // table
  const cols = ["Scenario", "Start", "End", "Years", "Invested", "Final value", "Net gain", "Total growth", "CAGR", "IRR", "Max DD"];
  const row = (name, m, base) => [name, monthLabel(monthStr(base.start)), monthLabel(monthStr(base.end)), (Math.round(base.years * 100) / 100).toString(),
    `${cur}${num(m.invested)}`, `${cur}${num(m.final)}`, `${cur}${num(m.net_gain)}`, pct(m.net_gain_pct, 1),
    m.cagr != null ? pct(m.cagr, 2) : "—", m.irr != null ? pct(m.irr, 2) : "—", pct(m.max_dd, 1)];
  const body = [];
  for (const r of runs) { body.push(row(r.name, r.m, r.m)); for (const c of r.comparisons) body.push(row(`↳ ${c.label}`, c.m, r.m)); }
  $("#summary").innerHTML = `<tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr>` + body.map((b) => `<tr>${b.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("");
  $("#modeNote").innerHTML = `${esc(IDX.name)} — all figures in <b>${esc(IDX.currency)}</b>, <b>${S.mode === "Nominal" ? "nominal terms" : "inflation-adjusted terms (start-of-period purchasing power)"}</b>. Price return only, excludes dividends.`;

  // downloads
  const dl = $("#downloads"); dl.innerHTML = "";
  for (const r of runs) {
    const b = document.createElement("button"); b.className = "btn"; b.textContent = `⬇️ Download CSV — ${r.name}`;
    b.onclick = () => downloadCSV(r, cpiLabel, rate);
    dl.appendChild(b);
  }
}

function downloadCSV(r, cpiLabel, rate) {
  const IDX = INDICES[S.index], m = (META.indices || {})[S.index] || {}, p = r.params;
  const extra = r.comparisons.map((c) => (c.key === "fixed" ? "fixed_return_value" : S.mode === "Nominal" ? "cash_value" : "cash_value_real"));
  let csv = `# Scenario: ${r.name}\n# Start: ${ymd(r.m.start)}\n# End: ${ymd(r.m.end)}\n# Index: ${IDX.name} (${m.ticker || ""}, ${IDX.currency})\n`
    + `# Value mode: ${S.mode}\n# Price return only, excludes dividends\n# Initial: ${p.initial}\n# Contribution: ${p.contribution} (${p.frequency})\n# Escalation: ${p.escalation / 100}\n`
    + (S.cmpFixed ? `# Fixed annual return: ${rate}\n` : "") + (S.cmpCash ? `# Cash: 0% interest, inflation = ${cpiLabel}\n` : "");
  csv += ["date", "contribution", "portfolio", "invested", "drawdown", ...extra].join(",") + "\n";
  r.rows.forEach((x, i) => {
    csv += [ymd(x.t), x.contribution, x.portfolio, x.invested, x.drawdown, ...r.comparisons.map((c) => Math.round(c.values[i] * 100) / 100)].join(",") + "\n";
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `${S.index}_${r.name.replace(/ /g, "_").replace(/[()]/g, "")}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ---------------- sidebar ---------------- */
function chips(id, values, get, set) {
  const box = $(id); box.innerHTML = "";
  for (const v of values) {
    const b = document.createElement("button"); b.type = "button"; b.className = "chip"; b.textContent = v;
    b.setAttribute("aria-pressed", get() === v);
    b.onclick = () => { set(v); box.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", c.textContent === get())); update(); };
    box.appendChild(b);
  }
}

function renderScenarioForms() {
  const box = $("#scenarios"); box.innerHTML = "";
  const IDX = INDICES[S.index], cur = CUR_SYM[IDX.currency] || "";
  S.scenarios.forEach((sc, i) => {
    const d = document.createElement("details"); d.className = "scen"; d.open = sc._open ?? i === 0;
    d.ontoggle = () => { sc._open = d.open; };
    d.innerHTML = `<summary>Scenario ${i + 1}: ${esc(sc.type)}</summary><div class="body">
      <label class="field">Type <select data-k="type">${["Lump sum", "DCA", "Escalated DCA", "Custom"].map((t) => `<option ${t === sc.type ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      <label class="check"><input type="checkbox" data-k="useWindow" ${sc.useWindow ? "checked" : ""}> Use the time window from the chart</label>
      <p class="hint win-note" ${sc.useWindow ? "" : "hidden"}>${S.winStart ? `📅 ${monthLabel(S.winStart)} – ${monthLabel(S.winEnd)} (set on the chart)` : ""}</p>
      <div class="own" ${sc.useWindow ? "hidden" : ""}>
        <label class="field">Start date (YYYY-MM-DD) <input type="text" inputmode="numeric" data-k="start" value="${esc(sc.start ?? ymd(Math.max(Date.UTC(1999, 0, 1), MIN_DATE)))}"></label>
        <label class="field">Duration (years) <input type="number" min="1" max="100" step="1" data-k="years" value="${sc.years}"></label>
      </div>
      <label class="field">Initial capital (${cur}) <input type="number" min="0" step="1000" data-k="initial" value="${sc.initial}"></label>
      <label class="field">Recurring contribution (${cur}) <input type="number" min="0" step="500" data-k="contribution" value="${sc.contribution}"></label>
      <label class="field">Contribution frequency <select data-k="frequency">${["Yearly", "Quarterly", "Monthly"].map((t) => `<option ${t === sc.frequency ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      <label class="field">Contribution escalation (% per year) <input type="number" min="0" max="20" step="0.5" data-k="escalation" value="${sc.escalation}"></label>
      <p class="err" data-i="${i}"></p>
      ${S.scenarios.length > 1 ? `<button class="btn ghost full" data-remove>🗑️ Remove scenario ${i + 1}</button>` : ""}
    </div>`;
    d.querySelectorAll("[data-k]").forEach((el) => {
      const k = el.dataset.k;
      const handler = () => {
        if (k === "type") { sc.type = el.value; if (el.value !== "Custom") Object.assign(sc, scenarioDefaults(el.value)); renderScenarioForms(); update(); return; }
        if (k === "useWindow") { sc.useWindow = el.checked; d.querySelector(".own").hidden = el.checked; d.querySelector(".win-note").hidden = !el.checked; }
        else if (k === "start") { sc.start = el.value; }
        else if (k === "frequency") { sc.frequency = el.value; }
        else {
          let v = parseFloat(el.value); if (!Number.isFinite(v)) v = 0;
          if (k === "years") v = Math.max(1, Math.min(100, Math.round(v)));
          if (k === "escalation") v = Math.max(0, Math.min(20, v));
          if (k === "initial" || k === "contribution") v = Math.max(0, v);
          sc[k] = v;
        }
        update();
      };
      el.addEventListener("change", handler);
    });
    const rm = d.querySelector("[data-remove]");
    if (rm) rm.onclick = () => { S.scenarios.splice(i, 1); renderScenarioForms(); update(); };
    box.appendChild(d);
  });
  $("#addScenario").hidden = S.scenarios.length >= 3;
}

function buildSidebar() {
  const sel = $("#index");
  sel.innerHTML = AVAILABLE.map((k) => `<option value="${k}">${esc(INDICES[k].name)}</option>`).join("");
  sel.value = S.index;
  sel.onchange = () => { S.index = sel.value; renderScenarioForms(); update(); };
  chips("#mode", ["Nominal", "Inflation-adjusted"], () => S.mode, (v) => { S.mode = v; });
  chips("#scale", ["Linear", "Log"], () => S.scale, (v) => { S.scale = v; });
  chips("#scope", ["Full history", "Selected window"], () => S.scope, (v) => { S.scope = v; });
  $("#trend").onchange = (e) => { S.trend = e.target.value; update(); };
  $("#degree").oninput = (e) => { S.degree = +e.target.value; $("#degreeVal").textContent = S.degree; };
  $("#degree").onchange = () => update();
  $("#addScenario").onclick = () => { S.scenarios.push(newScenario("DCA")); renderScenarioForms(); update(); };
  $("#cmpFixed").onchange = (e) => { S.cmpFixed = e.target.checked; $("#cmpRate").disabled = !S.cmpFixed; update(); };
  $("#cmpRate").disabled = true;
  $("#cmpRate").onchange = (e) => { let v = parseFloat(e.target.value); if (!Number.isFinite(v)) v = 10; S.cmpRate = Math.max(-50, Math.min(50, v)); e.target.value = S.cmpRate; update(); };
  $("#cmpCash").onchange = (e) => { S.cmpCash = e.target.checked; update(); };
  $("#showBears").disabled = !BEARS.length;
  $("#showBears").onchange = (e) => { S.showBears = e.target.checked; $("#showCauses").disabled = !S.showBears; update(); };
  $("#showCauses").onchange = (e) => { S.showCauses = e.target.checked; update(); };
  $("#bearHelpBtn").onclick = (e) => { const box = $("#bearHelp"); box.hidden = !box.hidden; e.currentTarget.setAttribute("aria-expanded", !box.hidden); };
  renderScenarioForms();
}

function openSettings(open) {
  $("#settings").classList.toggle("open", open);
  $("#backdrop").hidden = !open;
  $("#menuBtn").setAttribute("aria-expanded", open);
}

/* ---------------- main update ---------------- */
function update() {
  const IDX = INDICES[S.index];
  document.title = `${IDX.name} Backtester`;
  $("#title").textContent = `📈 ${IDX.name} Backtester`;
  $("#indexShort").textContent = IDX.short;
  $("#degreeBox").hidden = S.trend !== "Polynomial";
  $("#scopeBox").hidden = S.trend === "None";
  DF = indexFrame(S.index, S.mode);
  VALUE = S.mode === "Nominal" ? "nominal" : "real";
  if (DF.length < 2) {
    $("#warnings").innerHTML = `<div class="notice warn-box">No ${S.mode.toLowerCase()} data is available for ${esc(IDX.name)} at the moment. Please choose Nominal or another index.</div>`;
    $("#results").hidden = true;
    return;
  }
  MONTHS = DF.map((r) => monthStr(r.t)); N = MONTHS.length;
  MIN_DATE = DF[0].t; MAX_DATE = DF[N - 1].t;
  const [si, ei] = resolveWindow();
  renderHistory(si, ei);
  renderIndexInfo();
  document.querySelectorAll(".win-note").forEach((el) => { el.textContent = `📅 ${monthLabel(S.winStart)} – ${monthLabel(S.winEnd)} (set on the chart)`; });
  renderResults();
}

async function init() {
  const [csv, meta, idx] = await Promise.all([
    fetch("data/index_prices.csv").then((r) => r.text()),
    fetch("data/metadata.json").then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
    fetch("data/indices.json").then((r) => r.json()),
    fetch("data/bear_markets.json").then((r) => (r.ok ? r.json() : [])).then((b) => { BEARS = b; }).catch(() => {}),
  ]);
  ALL = parseCSV(csv); META = meta; INDICES = idx.indices; CUR_SYM = idx.currency_symbol;
  AVAILABLE = Object.keys(INDICES).filter((k) => ALL[k] && ALL[k].length);
  if (!AVAILABLE.includes(S.index)) S.index = AVAILABLE[0];
  S.scenarios = [newScenario("Lump sum")];
  buildSidebar();
  renderGuide();
  $("#back1").onclick = () => shiftWindow(-12);
  $("#fwd1").onclick = () => shiftWindow(12);
  $("#menuBtn").onclick = () => openSettings(true);
  $("#closeSettings").onclick = $("#backdrop").onclick = $("#applySettings").onclick = () => openSettings(false);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") openSettings(false); });
  $("#loading").hidden = true; $("#app").hidden = false;
  update();
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", update);
}
init().catch((e) => { console.error(e); $("#loading").textContent = "Could not load the data. Check your connection and reload the page."; });

if ("serviceWorker" in navigator) {
  // When a new version of the app is installed, reload once so it shows right away.
  const hadController = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController && !reloaded) { reloaded = true; location.reload(); }
  });
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").then((r) => r.update()).catch(() => {}));
}
