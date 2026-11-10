"""Static catalogue: periods, scenarios and KPI definitions.

This file is the single source of truth for what the GUI can show.
The KPI list is a PLACEHOLDER until the final list is fixed at the PDR (WP3, Zengqi / Tala).
"""

HISTORICAL_PERIODS = ["1991-2000", "2001-2010", "2011-2020"]
FUTURE_PERIODS = ["2021-2030", "2031-2040", "2041-2050"]
PERIODS = HISTORICAL_PERIODS + FUTURE_PERIODS
BASELINE_PERIOD = "2011-2020"  # reference for "change vs baseline" (to confirm at PDR)

SCENARIOS = {
    "historical": "Observed past (reanalysis)",
    "rcp45": "RCP4.5 – intermediate emissions",
    "rcp85": "RCP8.5 – high emissions",
}

# family: climate | virtual | simulated  (the three KPI families agreed with the supervisor)
# audience: which interface shows it. palette: sequential colour ramp for the map.
KPIS = [
    {"code": "t_mean", "name": "Mean air temperature", "unit": "°C", "family": "climate",
     "audience": ["expert", "kiosk"], "decimals": 1, "domain": [0, 20], "palette": "warm",
     "plain": "How warm the year is on average."},
    {"code": "hdd", "name": "Heating degree-days (base 20 °C)", "unit": "K·day", "family": "climate",
     "audience": ["expert"], "decimals": 0, "domain": [500, 4500], "palette": "cool",
     "plain": "How much heating a building needs over the year."},
    {"code": "cdd", "name": "Cooling degree-days (base 24 °C)", "unit": "K·day", "family": "climate",
     "audience": ["expert"], "decimals": 0, "domain": [0, 400], "palette": "warm",
     "plain": "How much cooling a building needs over the year."},
    {"code": "hot_days", "name": "Hot days (Tmax > 30 °C)", "unit": "days/yr", "family": "climate",
     "audience": ["expert", "kiosk"], "decimals": 0, "domain": [0, 90], "palette": "warm",
     "plain": "Days hotter than 30 °C."},
    {"code": "tropical_nights", "name": "Tropical nights (Tmin > 20 °C)", "unit": "nights/yr", "family": "climate",
     "audience": ["expert", "kiosk"], "decimals": 0, "domain": [0, 90], "palette": "warm",
     "plain": "Nights that never drop below 20 °C: hard to sleep without cooling."},
    {"code": "frost_days", "name": "Frost days (Tmin < 0 °C)", "unit": "days/yr", "family": "climate",
     "audience": ["expert"], "decimals": 0, "domain": [0, 150], "palette": "cool",
     "plain": "Days with freezing temperatures."},
    {"code": "ghi", "name": "Annual global horizontal irradiation", "unit": "kWh/m²·yr", "family": "climate",
     "audience": ["expert"], "decimals": 0, "domain": [1100, 1900], "palette": "warm",
     "plain": "Solar energy reaching the ground in one year."},
    {"code": "vb_overheat", "name": "Overheating hours – virtual building", "unit": "h/yr", "family": "virtual",
     "audience": ["expert", "kiosk"], "decimals": 0, "domain": [0, 1500], "palette": "warm",
     "plain": "Hours a typical flat is too hot inside without air conditioning."},
]
KPI_BY_CODE = {k["code"]: k for k in KPIS}

# Reference building for the kiosk comparison ("no action" vs "one adaptation action").
# The real model is the supervisor-provided IDF; these labels are placeholders.
REFERENCE_BUILDING = {
    "name": "Reference apartment block (1970s)",
    "cases": {
        "no_action": "No adaptation",
        "adapted": "External shading + night ventilation",
    },
    "kpis": [
        {"code": "cooling_need", "name": "Cooling need", "unit": "kWh/m²·yr"},
        {"code": "heating_need", "name": "Heating need", "unit": "kWh/m²·yr"},
        {"code": "overheat_hours", "name": "Overheating hours", "unit": "h/yr"},
    ],
}
