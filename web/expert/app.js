import { getJSON, rampStops, colorFor, fmt, readState, writeState, trendChart } from "/shared/wedo.js";

const state = readState({ kpi: "hdd", period: "2041-2050", scenario: "rcp45", mode: "absolute", unit: "" });
let meta, map, geo, values = {};
const $ = (id) => document.getElementById(id);

init().catch((e) => { document.body.insertAdjacentHTML("afterbegin", `<p class="error">${e.message}</p>`); });

async function init() {
  meta = await getJSON("/meta");
  geo = await (await fetch("/data/units.geojson")).json();
  buildControls();
  await buildMap();
  await refreshMap();
  if (state.unit) openUnit(state.unit);
}

// ---------------- controls ----------------
function isFuture(p) { return meta.future_periods.includes(p); }
function kpiDef(code = state.kpi) { return meta.kpis.find((k) => k.code === code); }

function buildControls() {
  const fam = { climate: "Climate KPIs", virtual: "Virtual-building KPIs" };
  $("kpi").innerHTML = Object.entries(fam).map(([f, label]) =>
    `<optgroup label="${label}">${meta.kpis.filter((k) => k.family === f && k.audience.includes("expert"))
      .map((k) => `<option value="${k.code}">${k.name}</option>`).join("")}</optgroup>`).join("");
  $("kpi").value = state.kpi;
  $("kpi").onchange = (e) => update({ kpi: e.target.value });

  const periods = [...meta.historical_periods, ...meta.future_periods];
  $("periods").innerHTML = periods.map((p) =>
    `<button data-p="${p}" class="${isFuture(p) ? "fut" : ""}">${p.replace("-", "–")}</button>`).join("");
  $("periods").onclick = (e) => e.target.dataset.p && update({ period: e.target.dataset.p });

  $("scenarios").innerHTML = ["rcp45", "rcp85"].map((s) =>
    `<button data-s="${s}" title="${meta.scenarios[s]}">${s === "rcp45" ? "RCP4.5 intermediate" : "RCP8.5 high"}</button>`).join("");
  $("scenarios").onclick = (e) => e.target.dataset.s && update({ scenario: e.target.dataset.s });
  $("modes").onclick = (e) => e.target.dataset.mode && update({ mode: e.target.dataset.mode });

  let t;
  $("search").oninput = (e) => {
    clearTimeout(t);
    const q = e.target.value.trim();
    if (!q) { $("search-results").innerHTML = ""; return; }
    t = setTimeout(async () => {
      const hits = await getJSON("/units/search", { q });
      $("search-results").innerHTML = hits.map((h) =>
        `<li role="option" data-u="${h.unit_id}">${h.name} <small>${h.region}</small></li>`).join("") || "<li>No match</li>";
    }, 200);
  };
  $("search-results").onclick = (e) => {
    const li = e.target.closest("li[data-u]"); if (!li) return;
    $("search-results").innerHTML = ""; $("search").value = li.textContent.split(" ")[0];
    const f = geo.features.find((f) => f.properties.unit_id === li.dataset.u);
    map.flyTo({ center: [f.properties.lon, f.properties.lat], zoom: 7 });
    openUnit(li.dataset.u);
  };
  $("panel-close").onclick = () => { selectUnit(""); };
  syncControls();
}

function syncControls() {
  const fut = isFuture(state.period);
  document.querySelectorAll("#periods button").forEach((b) => b.classList.toggle("on", b.dataset.p === state.period));
  document.querySelectorAll("#scenarios button").forEach((b) => {
    b.classList.toggle("on", fut && b.dataset.s === state.scenario); b.disabled = !fut;
  });
  $("scenario-help").textContent = fut ? meta.scenarios[state.scenario] : "Past periods use observed data (no scenario).";
  document.querySelectorAll("#modes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === state.mode));
  $("kpi-help").textContent = kpiDef().plain;
}

async function update(patch) {
  Object.assign(state, patch);
  writeState(state);
  syncControls();
  await refreshMap();
  if (state.unit) openUnit(state.unit);
}

// ---------------- map ----------------
async function buildMap() {
  const blank = { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef2f3" } }] };
  let style = blank;
  try {   // optional basemap; the platform works without it (e.g. offline)
    const r = await fetch("https://tiles.openfreemap.org/styles/positron", { signal: AbortSignal.timeout(2500) });
    if (r.ok) style = "https://tiles.openfreemap.org/styles/positron";
  } catch (_) { /* keep blank style */ }

  map = new maplibregl.Map({ container: "map", style, center: [12.5, 42.0], zoom: 4.8, minZoom: 4, maxZoom: 11,
                              attributionControl: { compact: true } });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  await new Promise((r) => map.on("load", r));
  map.addSource("units", { type: "geojson", data: geo, promoteId: "unit_id",
                           attribution: "Boundaries: ISTAT via openpolis (CC-BY) · values: SYNTHETIC" });
  const firstSymbol = (map.getStyle().layers || []).find((l) => l.type === "symbol")?.id; // keep basemap labels on top
  map.addLayer({ id: "units-fill", type: "fill", source: "units",
    paint: { "fill-color": ["coalesce", ["feature-state", "color"], "#cccccc"], "fill-opacity": 0.82 } }, firstSymbol);
  map.addLayer({ id: "units-line", type: "line", source: "units",
    paint: { "line-color": ["case", ["boolean", ["feature-state", "selected"], false], "#111", "#ffffff"],
             "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.5, 0.6] } }, firstSymbol);

  const tip = $("tooltip");
  map.on("mousemove", "units-fill", (e) => {
    const p = e.features[0].properties, k = kpiDef();
    tip.hidden = false; tip.style.left = e.point.x + 12 + "px"; tip.style.top = e.point.y + 12 + "px";
    tip.innerHTML = `<b>${p.name}</b><br>${fmt(values[p.unit_id], k.decimals, state.mode === "change")} ${k.unit}`;
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "units-fill", () => { tip.hidden = true; map.getCanvas().style.cursor = ""; });
  map.on("click", "units-fill", (e) => openUnit(e.features[0].properties.unit_id));
}

async function refreshMap() {
  const scenario = isFuture(state.period) ? state.scenario : "historical";
  const res = await getJSON("/map", { kpi: state.kpi, period: state.period, scenario, mode: state.mode });
  values = res.values;
  const k = kpiDef(), stops = rampStops(k, state.mode);
  for (const [id, v] of Object.entries(values)) map.setFeatureState({ source: "units", id }, { color: colorFor(stops, v) });
  drawLegend(k, stops);
  $("source").textContent = isFuture(state.period)
    ? `Source: projection, ${meta.scenarios[scenario]} · prototype synthetic values`
    : "Source: observed past (reanalysis) · prototype synthetic values";
}

function drawLegend(k, stops) {
  const title = state.mode === "change" ? `Change vs ${meta.baseline_period}` : k.name;
  const grad = `linear-gradient(90deg, ${stops.map((s) => s[1]).join(",")})`;
  $("legend").innerHTML = `<div class="lt">${title} <small>(${k.unit})</small></div>
    <div class="bar" style="background:${grad}"></div>
    <div class="lab"><span>${fmt(stops[0][0], k.decimals, state.mode === "change")}</span>
      <span>${fmt(stops[stops.length - 1][0], k.decimals, state.mode === "change")}${state.mode === "absolute" ? "+" : ""}</span></div>
    <p class="help">Fixed scale per indicator, so periods and scenarios can be compared.</p>`;
}

// ---------------- location panel ----------------
function selectUnit(id) {
  if (state.unit) map.setFeatureState({ source: "units", id: state.unit }, { selected: false });
  state.unit = id; writeState(state);
  if (id) map.setFeatureState({ source: "units", id }, { selected: true });
  $("panel-body").hidden = !id; $("panel-empty").hidden = !!id;
  document.body.classList.toggle("has-panel", !!id);
}

async function openUnit(id) {
  selectUnit(id);
  const scenario = isFuture(state.period) ? state.scenario : "historical";
  const s = await getJSON(`/units/${id}`, { period: state.period, scenario });
  $("unit-name").textContent = s.unit.name;
  $("unit-sub").textContent = `${s.unit.region} · ${state.period.replace("-", "–")} · ${isFuture(state.period) ? meta.scenarios[scenario] : "observed"}`;
  $("cmp-label").textContent = `baseline ${s.baseline_period} → ${state.period}`;
  $("kpi-cards").innerHTML = s.kpis.map((r) => {
    const k = kpiDef(r.code), up = r.change > 0;
    return `<button class="card ${r.code === state.kpi ? "on" : ""}" data-k="${r.code}" title="${k.plain}">
      <span class="kn">${k.name}</span>
      <span class="kv">${fmt(r.selected.value, k.decimals)} <small>${k.unit}</small></span>
      <span class="kc ${up ? "up" : "down"}">${fmt(r.change, k.decimals, true)} vs ${fmt(r.baseline.value, k.decimals)}</span>
      ${isFuture(state.period) ? `<span class="kr">range ${fmt(r.selected.min, k.decimals)}–${fmt(r.selected.max, k.decimals)}</span>` : ""}
    </button>`;
  }).join("");
  $("kpi-cards").onclick = (e) => { const c = e.target.closest("[data-k]"); if (c) update({ kpi: c.dataset.k }); };

  const k = kpiDef();
  const tr = await getJSON(`/units/${id}/trend`, { kpi: state.kpi, scenario: state.scenario });
  $("trend-label").textContent = `${k.name}, ${state.scenario.toUpperCase()}`;
  trendChart($("trend"), tr.points, { unit: k.unit, decimals: k.decimals });

  const epwQ = new URLSearchParams({ period: state.period, scenario });
  $("epw-link").href = `/api/units/${id}/epw?${epwQ}`;
  $("epw-help").textContent = `Hourly weather file for ${s.unit.name}, ${state.period}, ${isFuture(state.period) ? scenario.toUpperCase() : "observed"}. Prototype file: synthetic values.`;
  $("sim-cmd").textContent = `python wedo_sim.py run --idf my_building.idf --server ${location.origin} --unit ${id} --period ${state.period} --scenario ${scenario}`;
}

// ---------------- local results viewer (nothing is uploaded) ----------------
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); readResults(e.dataTransfer.files[0]); });
$("results-file").addEventListener("change", (e) => readResults(e.target.files[0]));

async function readResults(file) {
  if (!file) return;
  try {
    const r = JSON.parse(await file.text());
    if (r.schema !== "wedo-results/1") throw new Error("Not a We DO results file");
    const kpis = r.kpi_definitions;
    $("results").innerHTML = `<table class="res"><thead><tr><th>Case</th>${kpis.map((k) =>
      `<th>${k.name}<br><small>${k.unit}</small></th>`).join("")}<th>Run time</th></tr></thead><tbody>${
      r.cases.map((c) => `<tr><td>${c.label}${c.ok ? "" : " ⚠"}</td>${kpis.map((k) =>
        `<td>${c.ok ? fmt(c.kpis[k.code], k.unit.startsWith("h/") ? 0 : 1) : "–"}</td>`).join("")}<td>${fmt(c.runtime_s, 0)} s</td></tr>`).join("")}</tbody></table>
      <p class="help">Model: ${r.model.file} (${r.model.floor_area_m2 ? fmt(r.model.floor_area_m2, 0) + " m²" : "area n/a"}) ·
      EnergyPlus ${r.energyplus.version} · run on ${r.machine.cpus} CPUs.</p>`;
  } catch (e) {
    $("results").innerHTML = `<p class="error">Could not read the file: ${e.message}</p>`;
  }
}
