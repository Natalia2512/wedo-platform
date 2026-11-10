"""We DO prototype API (FastAPI).

Run:  cd api && uvicorn main:app --reload --port 8000
Docs: http://localhost:8000/docs   Expert site: /expert/   Kiosk: /kiosk/
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from catalog import (BASELINE_PERIOD, FUTURE_PERIODS, HISTORICAL_PERIODS, KPI_BY_CODE, KPIS,
                     REFERENCE_BUILDING, SCENARIOS)
from provider import MockProvider

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="We DO API (prototype)", version="0.1.0",
              description="Data contract between WP2/WP3 results and the WP4 interfaces. "
                          "Currently served by a MOCK provider with synthetic values.")
provider = MockProvider()


def _check(kpi: str | None = None, period: str | None = None, scenario: str | None = None):
    if kpi is not None and kpi not in KPI_BY_CODE:
        raise HTTPException(404, f"unknown kpi '{kpi}'")
    if period is not None and period not in HISTORICAL_PERIODS + FUTURE_PERIODS:
        raise HTTPException(404, f"unknown period '{period}'")
    if scenario is not None and scenario not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario '{scenario}'")
    if period in FUTURE_PERIODS and scenario == "historical":
        raise HTTPException(422, "future periods need scenario rcp45 or rcp85")


def _unit(unit_id: str) -> dict:
    try:
        return provider.unit(unit_id)
    except KeyError:
        raise HTTPException(404, f"unknown unit '{unit_id}'")


@app.get("/api/meta")
def meta():
    """Everything the interfaces need to build their selectors and legends."""
    return {"provider": provider.name, "historical_periods": HISTORICAL_PERIODS,
            "future_periods": FUTURE_PERIODS, "baseline_period": BASELINE_PERIOD,
            "scenarios": SCENARIOS, "kpis": KPIS, "reference_building": REFERENCE_BUILDING}


@app.get("/api/map")
def map_values(kpi: str, period: str, scenario: str = "historical",
               mode: str = Query("absolute", pattern="^(absolute|change)$")):
    """One value per spatial unit, used to colour the map: {unit_id: value}."""
    _check(kpi, period, scenario)
    return {"kpi": kpi, "period": period, "scenario": scenario, "mode": mode,
            "values": provider.map_values(kpi, period, scenario, mode)}


@app.get("/api/units/search")
def search(q: str = Query(..., min_length=1)):
    return provider.search(q)


@app.get("/api/units/{unit_id}")
def unit_summary(unit_id: str, period: str, scenario: str = "historical"):
    _unit(unit_id); _check(period=period, scenario=scenario)
    return provider.unit_summary(unit_id, period, scenario)


@app.get("/api/units/{unit_id}/trend")
def trend(unit_id: str, kpi: str, scenario: str = "rcp45"):
    _unit(unit_id); _check(kpi=kpi, scenario=scenario)
    return provider.trend(unit_id, kpi, scenario)


@app.get("/api/units/{unit_id}/building")
def building(unit_id: str, period: str, scenario: str = "rcp45"):
    """Precomputed reference-building results: no action vs one adaptation action (kiosk)."""
    _unit(unit_id); _check(period=period, scenario=scenario)
    return provider.building_comparison(unit_id, period, scenario)


@app.get("/api/units/{unit_id}/epw", response_class=PlainTextResponse)
def epw(unit_id: str, period: str, scenario: str = "historical"):
    u = _unit(unit_id); _check(period=period, scenario=scenario)
    name = f"WeDO_{u['acr']}_{period}_{'historical' if period in HISTORICAL_PERIODS else scenario}.epw"
    return PlainTextResponse(provider.epw_text(unit_id, period, scenario),
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/downloads/wedo_sim.py", include_in_schema=False)
def runner():
    """The local simulation runner the expert downloads (IDF never leaves their computer)."""
    return FileResponse(ROOT / "sim" / "wedo_sim.py", filename="wedo_sim.py")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/expert/")


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
