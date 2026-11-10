// Shared helpers for the expert site and the kiosk (no build step, plain ES module).

export const API = "/api";

export async function getJSON(path, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${API}${path}${qs ? "?" + qs : ""}`);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// ---------- colour scales (fixed per KPI so periods/scenarios are comparable) ----------
const RAMPS = {
  warm: ["#fff5d6", "#fdd38a", "#f9a04f", "#e8603c", "#b8283a", "#6e0f3a"],
  cool: ["#f2f7fb", "#c9dff0", "#8fbfe0", "#4f97c9", "#2266a8", "#0c3a73"],
  diverging: ["#2166ac", "#67a9cf", "#d1e5f0", "#f7f7f7", "#fddbc7", "#ef8a62", "#b2182b"],
};

export function rampStops(kpi, mode) {
  if (mode === "change") {
    const span = (kpi.domain[1] - kpi.domain[0]) * 0.35;
    const cols = RAMPS.diverging;
    return cols.map((c, i) => [-span + (2 * span * i) / (cols.length - 1), c]);
  }
  const cols = RAMPS[kpi.palette] || RAMPS.warm;
  const [a, b] = kpi.domain;
  return cols.map((c, i) => [a + ((b - a) * i) / (cols.length - 1), c]);
}

export function colorFor(stops, v) {
  if (v == null || Number.isNaN(v)) return "#cccccc";
  if (v <= stops[0][0]) return stops[0][1];
  for (let i = 1; i < stops.length; i++) {
    if (v <= stops[i][0]) {
      const [x0, c0] = stops[i - 1], [x1, c1] = stops[i];
      return mix(c0, c1, (v - x0) / (x1 - x0));
    }
  }
  return stops[stops.length - 1][1];
}

function mix(a, b, t) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return "#" + pa.map((x, i) => Math.round(x + (pb[i] - x) * t).toString(16).padStart(2, "0")).join("");
}

export function fmt(v, decimals = 0, signed = false) {
  if (v == null) return "–";
  const s = Number(v).toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return signed && v > 0 ? "+" + s : s;
}

// ---------- URL state: any view can be shared or opened from a QR code ----------
export function readState(defaults) {
  const p = new URLSearchParams(location.search);
  const s = { ...defaults };
  for (const k of Object.keys(defaults)) if (p.has(k)) s[k] = p.get(k);
  return s;
}
export function writeState(state) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) if (v != null && v !== "") p.set(k, v);
  history.replaceState(null, "", `${location.pathname}?${p}`);
}

// ---------- small SVG line chart with uncertainty band ----------
export function trendChart(el, points, { unit = "", decimals = 0, splitYear = 2020, height = 220 } = {}) {
  const W = el.clientWidth || 360, H = height, m = { l: 46, r: 12, t: 12, b: 26 };
  const xs = points.map((p) => p.year);
  const ys = points.flatMap((p) => [p.value, p.min, p.max]).filter((v) => v != null);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  const pad = (y1 - y0) * 0.08 || 1; y0 -= pad; y1 += pad;
  const X = (x) => m.l + ((x - x0) / (x1 - x0)) * (W - m.l - m.r);
  const Y = (y) => H - m.b - ((y - y0) / (y1 - y0)) * (H - m.t - m.b);
  const band = points.filter((p) => p.min != null);
  const bandPath = band.length
    ? "M" + band.map((p) => `${X(p.year)},${Y(p.max)}`).join("L") + "L" +
      band.slice().reverse().map((p) => `${X(p.year)},${Y(p.min)}`).join("L") + "Z" : "";
  const line = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${X(p.year)},${Y(p.value)}`).join("");
  const past = points.filter((p) => p.year <= splitYear);
  const fut = points.filter((p) => p.year >= splitYear);
  const ticksY = [0, 1, 2, 3, 4].map((i) => y0 + ((y1 - y0) * i) / 4);
  const ticksX = [1991, 2000, 2010, 2020, 2030, 2040, 2050].filter((t) => t >= x0 && t <= x1);
  el.innerHTML = `
  <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="Trend chart">
    ${ticksY.map((t) => `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(t)}" y2="${Y(t)}" class="grid"/>
      <text x="${m.l - 6}" y="${Y(t) + 4}" class="tick" text-anchor="end">${fmt(t, decimals)}</text>`).join("")}
    ${ticksX.map((t) => `<text x="${X(t)}" y="${H - 8}" class="tick" text-anchor="middle">${t}</text>`).join("")}
    <line x1="${X(splitYear)}" x2="${X(splitYear)}" y1="${m.t}" y2="${H - m.b}" class="split"/>
    <text x="${X(splitYear) + 4}" y="${m.t + 10}" class="tick">projection →</text>
    ${bandPath ? `<path d="${bandPath}" class="band"/>` : ""}
    <path d="${line(past)}" class="past"/>
    <path d="${line(fut)}" class="future"/>
    <text x="${m.l}" y="${m.t - 2}" class="tick">${unit}</text>
  </svg>`;
}

// ---------- idle reset (kiosk) ----------
export function onIdle(ms, cb) {
  let t;
  const reset = () => { clearTimeout(t); t = setTimeout(cb, ms); };
  ["pointerdown", "keydown", "wheel"].forEach((ev) => addEventListener(ev, reset, { passive: true }));
  reset();
  return reset;
}
