import { getJSON, fmt, onIdle } from "/shared/wedo.js";

// Kiosk = prepared results only (FREQ_8): every number comes from precomputed API responses.
const FUTURE = "2041-2050";
const QUICK = ["001", "015", "058", "063", "072", "082", "118", "048"]; // Torino, Milano, Roma, Napoli, Bari, Palermo, Cagliari, Firenze
const IDLE_MS = 120000;
const s = { unit: null, name: "", scenario: "rcp85", guess: null };
let meta, geo, kmap;
const $ = (id) => document.getElementById(id);

init();

async function init() {
  meta = await getJSON("/meta");
  geo = await (await fetch("/data/units.geojson")).json();
  document.addEventListener("click", (e) => { const g = e.target.closest("[data-go]"); if (g) go(g.dataset.go); });
  $("quick").innerHTML = QUICK.map((id) => {
    const f = geo.features.find((f) => f.properties.unit_id === id);
    return f ? `<button class="big" data-u="${id}">${f.properties.name}</button>` : "";
  }).join("");
  $("quick").onclick = (e) => { const b = e.target.closest("[data-u]"); if (b) choose(b.dataset.u); };
  $("scen").onclick = (e) => { const b = e.target.closest("[data-s]"); if (b) { s.scenario = b.dataset.s; renderReveal(); } };
  onIdle(IDLE_MS, () => go("attract"));            // FREQ_13-style reset after 2 min without touches
  go("attract");
}

function go(screen) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.toggle("on", el.dataset.s === screen));
  const order = ["place", "guess", "reveal", "building", "home"];
  document.querySelectorAll("#dots li").forEach((li, i) => li.classList.toggle("on", i <= order.indexOf(screen)));
  if (screen === "attract") { Object.assign(s, { unit: null, scenario: "rcp85", guess: null }); $("k-source").textContent = ""; }
  if (screen === "place") ensureMap();
  if (screen === "reveal") renderReveal();
  if (screen === "building") renderBuilding();
  if (screen === "home") renderQR();
}

function ensureMap() {
  if (kmap) { kmap.resize(); return; }
  kmap = new maplibregl.Map({
    container: "kmap", center: [12.6, 41.9], zoom: 4.6, minZoom: 4.3, maxZoom: 7, dragRotate: false, pitchWithRotate: false,
    style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#dcecf4" } }] },
    attributionControl: false,
  });
  kmap.touchZoomRotate.disableRotation();
  kmap.fitBounds([[6.6, 36.6], [18.6, 47.1]], { padding: 20, animate: false });
  kmap.on("load", async () => {
    kmap.addSource("u", { type: "geojson", data: geo, promoteId: "unit_id" });
    const hot = await getJSON("/map", { kpi: "hot_days", period: FUTURE, scenario: "rcp85" });
    const expr = ["match", ["get", "unit_id"]];
    for (const [id, v] of Object.entries(hot.values)) expr.push(id, v);
    expr.push(0);
    kmap.addLayer({ id: "f", type: "fill", source: "u", paint: { "fill-color":
      ["interpolate", ["linear"], expr, 0, "#fff5d6", 20, "#f9a04f", 40, "#e8603c", 60, "#b8283a", 80, "#6e0f3a"], "fill-opacity": 0.9 } });
    kmap.addLayer({ id: "l", type: "line", source: "u", paint: { "line-color": "#fff", "line-width": 0.8 } });
    kmap.on("click", "f", (e) => choose(e.features[0].properties.unit_id));
  });
}

async function choose(id) {
  const f = geo.features.find((f) => f.properties.unit_id === id);
  s.unit = id; s.name = f.properties.name;
  // prediction before the result (UREQ_8)
  const today = await getJSON(`/units/${id}`, { period: meta.baseline_period, scenario: "historical" });
  const fut = await getJSON(`/units/${id}`, { period: FUTURE, scenario: "rcp85" });
  const now = today.kpis.find((k) => k.code === "hot_days").selected.value;
  const then = fut.kpis.find((k) => k.code === "hot_days").selected.value;
  s.truth = then;
  const opts = [then];
  for (const c of [Math.round(now * 0.8), Math.round(then * 1.8 + 5), then + 12, then + 25]) {
    if (opts.length < 3 && c >= 0 && !opts.includes(c)) opts.push(c);
  }
  shuffle(opts).forEach((v, i) => (opts[i] = v));
  $("guess-q").textContent = `How many very hot days (above 30 °C) will ${s.name} have each year in the 2040s?`;
  $("guess-today").textContent = `Today it has about ${fmt(now)} per year. Make your guess!`;
  $("choices").innerHTML = opts.map((o) => `<button class="big choice" data-v="${o}">${fmt(o)} days</button>`).join("");
  $("choices").onclick = (e) => { const b = e.target.closest("[data-v]"); if (b) { s.guess = +b.dataset.v; go("reveal"); } };
  go("guess");
}

async function renderReveal() {
  if (!s.unit) return go("place");
  document.querySelectorAll("#scen button").forEach((b) => b.classList.toggle("on", b.dataset.s === s.scenario));
  const [now, fut] = await Promise.all([
    getJSON(`/units/${s.unit}`, { period: meta.baseline_period, scenario: "historical" }),
    getJSON(`/units/${s.unit}`, { period: FUTURE, scenario: s.scenario })]);
  $("reveal-title").textContent = `${s.name}: today vs the 2040s`;
  if (s.guess != null) {
    const right = s.guess === s.truth;
    $("reveal-feedback").textContent = right ? `Well done! About ${fmt(s.truth)} hot days per year with rising emissions.`
      : `Not quite: it's about ${fmt(s.truth)} hot days per year if emissions keep rising.`;
  }
  const show = ["hot_days", "tropical_nights", "t_mean"];
  const max = { hot_days: 90, tropical_nights: 90, t_mean: 22 };
  $("compare").innerHTML = show.map((code) => {
    const k = meta.kpis.find((x) => x.code === code);
    const a = now.kpis.find((x) => x.code === code).selected.value, b = fut.kpis.find((x) => x.code === code).selected.value;
    const w = (v) => Math.max(2, Math.min(100, (v / max[code]) * 100));
    return `<div class="metric"><div class="m-name">${k.name}<span>${k.plain}</span></div>
      <div class="m-row"><span class="m-lab">Today</span><div class="m-bar now" style="width:${w(a)}%"></div><b>${fmt(a, k.decimals)}</b></div>
      <div class="m-row"><span class="m-lab">2040s</span><div class="m-bar fut" style="width:${w(b)}%"></div><b>${fmt(b, k.decimals)}</b></div></div>`;
  }).join("");
  $("k-source").textContent = `Data: ${now.source.dataset} · past: observed · future: ${meta.scenarios[s.scenario]}`;
}

async function renderBuilding() {
  const b = await getJSON(`/units/${s.unit}/building`, { period: FUTURE, scenario: s.scenario });
  const no = b.cases.no_action, ad = b.cases.adapted;
  const cut = Math.round((1 - ad.overheat_hours / Math.max(1, no.overheat_hours)) * 100);
  $("b-title").textContent = `A ${b.building.toLowerCase()} in ${s.name}, 2040s`;
  $("b-lead").textContent = `With ${b.labels.adapted.toLowerCase()}, the hours when the flat is too hot drop by about ${cut}%.`;
  const row = (k) => {
    const m = Math.max(no[k.code], ad[k.code], 1);
    return `<div class="c-kpi"><div class="c-name">${k.name} <small>${k.unit}</small></div>
      <div class="m-row"><span class="m-lab">${b.labels.no_action}</span><div class="m-bar now red" style="width:${(no[k.code] / m) * 100}%"></div><b>${fmt(no[k.code])}</b></div>
      <div class="m-row"><span class="m-lab">${b.labels.adapted}</span><div class="m-bar fut green" style="width:${(ad[k.code] / m) * 100}%"></div><b>${fmt(ad[k.code])}</b></div></div>`;
  };
  $("cases").innerHTML = b.kpis.filter((k) => k.code !== "heating_need").map(row).join("");
}

function renderQR() {
  const url = `${location.origin}/expert/?unit=${s.unit}&kpi=hot_days&period=${FUTURE}&scenario=${s.scenario}`;
  const qr = qrcode(0, "M"); qr.addData(url); qr.make();
  $("qr").innerHTML = qr.createSvgTag({ cellSize: 8, margin: 2, scalable: true });
}

function shuffle(a) { return a.map((v) => [Math.random(), v]).sort((x, y) => x[0] - y[0]).map((x) => x[1]); }
