"""Data providers.

The API only talks to a provider through the methods below (the "data contract").
MockProvider returns SYNTHETIC, deterministic values so the GUI and kiosk can be designed
before WP2/WP3 deliver real data. A DatabaseProvider with the same methods will replace it
after the PDR, without touching the API or the front-end.

None of the numbers produced here are real climate data.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from catalog import (BASELINE_PERIOD, FUTURE_PERIODS, HISTORICAL_PERIODS, KPI_BY_CODE, KPIS,
                     PERIODS, REFERENCE_BUILDING, SCENARIOS)

DATA_DIR = Path(__file__).resolve().parent.parent / "web" / "data"
MOUNTAIN = {"AO": 6.0, "BZ": 5.0, "TN": 4.5, "BL": 4.5, "SO": 4.0, "VB": 2.5, "CN": 1.5, "AQ": 3.5,
            "IS": 2.0, "PZ": 2.5, "RI": 1.5, "BI": 1.0, "UD": 1.0, "PN": 1.0}


def _noise(*parts) -> float:
    """Deterministic pseudo-random number in [-1, 1] from any key."""
    h = hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:8], 16) / 0x7FFFFFFF - 1.0


class MockProvider:
    name = "mock"

    def __init__(self) -> None:
        geo = json.loads((DATA_DIR / "units.geojson").read_text(encoding="utf-8"))
        self._units = {f["properties"]["unit_id"]: f["properties"] for f in geo["features"]}

    # ---------- metadata ----------
    def units(self) -> list[dict]:
        return list(self._units.values())

    def unit(self, unit_id: str) -> dict:
        if unit_id not in self._units:
            raise KeyError(unit_id)
        return self._units[unit_id]

    def search(self, q: str, limit: int = 10) -> list[dict]:
        q = q.strip().lower()
        hits = [u for u in self._units.values() if q in u["name"].lower() or q == u["acr"].lower()]
        return sorted(hits, key=lambda u: (not u["name"].lower().startswith(q), u["name"]))[:limit]

    # ---------- synthetic climate model ----------
    def _t_mean(self, u: dict, year: float, scenario: str) -> float:
        base = 13.0 + (45.0 - u["lat"]) * 0.55 - MOUNTAIN.get(u["acr"], 0.0)
        if year <= 2015 or scenario == "historical":
            trend = 0.03 * (year - 2015)                      # past warming
        else:
            rate = 0.025 if scenario == "rcp45" else 0.042    # °C per year after 2015
            trend = rate * (year - 2015)
        return base + trend

    def _kpis_from_t(self, u: dict, t: float, year: float) -> dict:
        lat = u["lat"]
        return {
            "t_mean": t,
            "hdd": max(0.0, (20.0 - t) * 365 * 1.02),
            "cdd": max(0.0, 18.0 * (t - 8.0)),
            "hot_days": max(0.0, 6.0 * (t - 9.5)),
            "tropical_nights": max(0.0, 9.0 * (t - 12.5)),
            "frost_days": max(0.0, 18.0 * (15.5 - t)),
            "ghi": 1250 + (46.0 - lat) * 55 + 0.6 * (year - 2015),
            "vb_overheat": max(0.0, 120.0 * (t - 10.0)),
        }

    def _period_mid(self, period: str) -> float:
        a, b = map(int, period.split("-"))
        return (a + b) / 2

    def _scenario_ok(self, period: str, scenario: str) -> str:
        if period in HISTORICAL_PERIODS:
            return "historical"
        if scenario not in ("rcp45", "rcp85"):
            raise ValueError("future periods need scenario rcp45 or rcp85")
        return scenario

    def _uncertainty(self, value: float, year: float, scenario: str, kpi: str = "") -> tuple[float, float]:
        ahead = max(0.0, year - 2020)
        if kpi == "t_mean":                       # absolute spread for temperature
            spread = (0.2 if scenario == "historical" else 0.3 + 0.03 * ahead)
        else:
            frac = 0.03 if scenario == "historical" else 0.05 + 0.004 * ahead
            spread = abs(value) * frac + 0.2
        return value - spread, value + spread

    def kpi_value(self, unit_id: str, kpi: str, period: str, scenario: str) -> dict:
        u = self.unit(unit_id)
        scn = self._scenario_ok(period, scenario)
        year = self._period_mid(period)
        v = self._kpis_from_t(u, self._t_mean(u, year, scn), year)[kpi]
        lo, hi = self._uncertainty(v, year, scn, kpi)
        d = KPI_BY_CODE[kpi]["decimals"]
        return {"value": round(v, d), "min": round(max(lo, 0) if kpi != "t_mean" else lo, d),
                "max": round(hi, d)}

    # ---------- contract methods used by the API ----------
    def map_values(self, kpi: str, period: str, scenario: str, mode: str = "absolute") -> dict:
        out = {}
        for uid in self._units:
            v = self.kpi_value(uid, kpi, period, scenario)["value"]
            if mode == "change":
                v = round(v - self.kpi_value(uid, kpi, BASELINE_PERIOD, "historical")["value"],
                          KPI_BY_CODE[kpi]["decimals"])
            out[uid] = v
        return out

    def unit_summary(self, unit_id: str, period: str, scenario: str) -> dict:
        rows = []
        for k in KPIS:
            now = self.kpi_value(unit_id, k["code"], BASELINE_PERIOD, "historical")
            sel = self.kpi_value(unit_id, k["code"], period, scenario)
            rows.append({"code": k["code"], "baseline": now, "selected": sel,
                         "change": round(sel["value"] - now["value"], k["decimals"])})
        return {"unit": self.unit(unit_id), "period": period, "scenario": self._scenario_ok(period, scenario),
                "baseline_period": BASELINE_PERIOD, "kpis": rows, "source": self.source(period, scenario)}

    def trend(self, unit_id: str, kpi: str, scenario: str) -> dict:
        u = self.unit(unit_id)
        d = KPI_BY_CODE[kpi]["decimals"]
        pts = []
        for year in range(1991, 2051):
            scn = "historical" if year <= 2020 else scenario
            t = self._t_mean(u, year, scn) + 0.6 * _noise(unit_id, year)  # year-to-year variability
            v = self._kpis_from_t(u, t, year)[kpi]
            lo, hi = self._uncertainty(v, year, scn, kpi) if year > 2020 else (None, None)
            pts.append({"year": year, "value": round(v, d),
                        "min": None if lo is None else round(lo, d), "max": None if hi is None else round(hi, d)})
        return {"unit_id": unit_id, "kpi": kpi, "scenario": scenario, "points": pts}

    def building_comparison(self, unit_id: str, period: str, scenario: str) -> dict:
        u = self.unit(unit_id)
        scn = self._scenario_ok(period, scenario)
        year = self._period_mid(period)
        t = self._t_mean(u, year, scn)
        k = self._kpis_from_t(u, t, year)
        no_action = {"cooling_need": 4.0 * max(0.0, t - 9.0) ** 1.3,
                     "heating_need": k["hdd"] * 0.045,
                     "overheat_hours": k["vb_overheat"] * 1.2}
        adapted = {"cooling_need": no_action["cooling_need"] * 0.62,
                   "heating_need": no_action["heating_need"] * 1.03,
                   "overheat_hours": no_action["overheat_hours"] * 0.45}
        rnd = lambda d: {key: round(val) for key, val in d.items()}
        return {"building": REFERENCE_BUILDING["name"], "period": period, "scenario": scn,
                "cases": {"no_action": rnd(no_action), "adapted": rnd(adapted)},
                "labels": REFERENCE_BUILDING["cases"], "kpis": REFERENCE_BUILDING["kpis"],
                "source": self.source(period, scenario)}

    def source(self, period: str, scenario: str) -> dict:
        hist = period in HISTORICAL_PERIODS
        return {"dataset": "SYNTHETIC MOCK DATA – not real climate data",
                "planned_dataset": "Reanalysis (to confirm at PDR)" if hist
                else "Regional climate projection (to confirm at PDR)",
                "scenario": "historical" if hist else scenario,
                "limitations": "Prototype values for interface design only."}

    def epw_text(self, unit_id: str, period: str, scenario: str) -> str:
        return synthetic_epw(self.unit(unit_id), self._t_mean(self.unit(unit_id), self._period_mid(period),
                                                               self._scenario_ok(period, scenario)),
                             label=f"{period} {self._scenario_ok(period, scenario)}")


def synthetic_epw(u: dict, t_mean: float, label: str) -> str:
    """A syntactically valid EPW (8 header lines + 8760 hourly rows, 35 fields) with synthetic weather.
    Good for testing the download and the local EnergyPlus runner, NOT for design."""
    lat, lon = u["lat"], u["lon"]
    header = [
        f"LOCATION,{u['name']},{u['region']},ITA,WeDO-SYNTHETIC,{u['unit_id']},{lat:.3f},{lon:.3f},1.0,100.0",
        "DESIGN CONDITIONS,0",
        "TYPICAL/EXTREME PERIODS,0",
        "GROUND TEMPERATURES,0",
        "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
        f"COMMENTS 1,We DO prototype – SYNTHETIC weather ({label}). Not real data.",
        "COMMENTS 2,Generated by api/provider.py for interface and runner testing only.",
        "DATA PERIODS,1,1,Data,Monday,1/1,12/31",
    ]
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    rows, doy = [], 0
    for m, nd in enumerate(days_in_month, start=1):
        for d in range(1, nd + 1):
            doy += 1
            seasonal = -9.0 * math.cos(2 * math.pi * (doy - 15) / 365)
            decl = math.radians(23.45) * math.sin(2 * math.pi * (284 + doy) / 365)
            for h in range(1, 25):
                solar_hour = h - 0.5 + (lon - 15.0) / 15.0          # local standard time UTC+1
                ha = math.radians(15 * (solar_hour - 12))
                cosz = (math.sin(math.radians(lat)) * math.sin(decl)
                        + math.cos(math.radians(lat)) * math.cos(decl) * math.cos(ha))
                cosz = max(cosz, 0.0)
                cloud = 0.5 + 0.5 * _noise(u["unit_id"], doy)        # 0..1
                ext = 1367 * cosz
                ghi = ext * (0.75 - 0.45 * cloud)
                dhi = ghi * (0.25 + 0.6 * cloud)
                dni = (ghi - dhi) / cosz if cosz > 0.05 else 0.0
                tdb = t_mean + seasonal + 4.5 * math.cos(2 * math.pi * (h - 15) / 24) + 1.5 * _noise(doy, h)
                rh = min(98.0, max(20.0, 62 + 20 * math.cos(2 * math.pi * (h - 4) / 24) + 10 * cloud))
                a, b = 17.62, 243.12
                g = math.log(rh / 100) + a * tdb / (b + tdb)
                tdp = b * g / (a - g)
                ir = 5.67e-8 * (0.75 + 0.2 * cloud) * (tdb + 273.15) ** 4
                ws = max(0.0, 2.5 + 1.5 * _noise("w", doy, h))
                wd = int((200 + 90 * _noise("d", doy)) % 360)
                sky = round(10 * cloud)
                rows.append(",".join(str(x) for x in [
                    2015, m, d, h, 60, "?9?9?9?9E0?9?9?9?9?9?9?9?9?9?9?9?9?9*9*9?9?9?9",
                    f"{tdb:.1f}", f"{tdp:.1f}", f"{rh:.0f}", 100800, f"{ext:.0f}", f"{1367 if cosz > 0 else 0}",
                    f"{ir:.0f}", f"{ghi:.0f}", f"{dni:.0f}", f"{dhi:.0f}", 999999, 999999, 999999, 9999,
                    wd, f"{ws:.1f}", sky, sky, 9999, 99999, 9, 999999999, 999, 0.999, 0, 88, 0.2, 0, 1]))
    return "\n".join(header + rows) + "\n"
