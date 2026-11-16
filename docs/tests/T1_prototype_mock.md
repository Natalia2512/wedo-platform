# T1 – End-to-end prototype on mock data (municipalities)

| Field | Value |
|---|---|
| Owner | Natalia |
| Date | 2026-11-16 |
| Status | done |
| Related requirement or decision | AD1 (precompute), AD6 (municipalities), map response target ≤ 3 s, TREQ_5 |
| Ran on | cloud sandbox, 2 CPUs, headless Chromium with software WebGL (slower than a normal PC) |
| Code | `api/`, `web/`, `sim/` (this repo) |
| Data location | synthetic values from `api/provider.py`; ISTAT municipality boundaries in `web/data/units.geojson` |

## Goal
Check that the architecture works at the real scale of Italian municipalities before the PDR: map size, API speed, browser speed, kiosk, local runner.

## Setup
Municipality boundaries from openpolis/geojson-italy, simplified with tolerance 0.003°. Prototype API served with uvicorn; browser tests with Playwright; load test with 10 concurrent clients for 20 s; local runner with a fake EnergyPlus (6 cases).

## Results

| Measure | Value | Unit |
|---|---|---|
| Municipalities | 7,896 | count |
| Geometry raw / simplified / gzip | 35.9 / 3.74 / 0.8 | MB |
| API map values, one user (median / p95) | 48 / 58 | ms |
| API map values payload (gzip) | 33 | KB |
| API place summary / trend | 1.7 / 2.2 | ms |
| EPW download | 1.62 MB in 126 | ms |
| 10 concurrent users, map values (median / p95) | 510 / 750 | ms |
| Throughput with 10 users | 19 | requests/s |
| Browser: change of KPI or decade (median of 5) | 533 | ms |
| Browser: first map view incl. external basemap | 5,173 | ms |
| Kiosk place screen | 746 | ms |
| Local runner, 6 cases, fake EnergyPlus | 2.4 | s |
| EPW files for 9 climate sets | 71,064 files, 115 | GB |

## Problems found
- The kiosk city buttons used province codes; fixed to municipality ISTAT codes.
- With 10 users the mock recomputes all values per request and slows down.
- Close zoom on one municipality is coarse with 0.003° simplification.

## Conclusion
Municipality scale is feasible: the map recolours well inside 3 s. Values must be precomputed (AD1): computing on request does not scale. Real EnergyPlus time is still to be measured (T2).

## Numbers for the architecture
units = 7896 · geo_gzip_mb = 0.8 · map_payload_kb = 34 · epw_mb = 1.62
