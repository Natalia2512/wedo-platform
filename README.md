# We DO – interface prototype (WP4, Natalia)

Interactive mock-up of the **expert platform** and the **public kiosk**, plus the **local simulation runner** for experts.
It runs on **synthetic data**: its purpose is to support the PDR (interface design, data contract, compute bounds),
not to be the final implementation. Real development starts after the architecture freeze at the PDR.

## Run it (any laptop, ~2 minutes)

Each person creates their own Python environment (it is not stored in Git). Python 3.10+.

Windows (PowerShell), from the `wedo-platform` folder:

```powershell
python -m venv C:\Users\<you>\wedo-venv            # outside OneDrive; ArcGIS users: use ArcGIS Pro's python.exe here
C:\Users\<you>\wedo-venv\Scripts\python.exe -m pip install -r requirements.txt
cd api
C:\Users\<you>\wedo-venv\Scripts\python.exe -m uvicorn main:app --port 8000
```

macOS / Linux:

```bash
python3 -m venv ~/wedo-venv
~/wedo-venv/bin/python -m pip install -r requirements.txt
cd api && ~/wedo-venv/bin/python -m uvicorn main:app --port 8000
```

Do not install the libraries into ArcGIS Pro's own environment.

- Expert site: http://localhost:8000/expert/
- Kiosk: http://localhost:8000/kiosk/ (best full screen, F11)
- API documentation (data contract): http://localhost:8000/docs

## What is in here

| Folder | Content |
|---|---|
| `api/catalog.py` | Periods (10-year), scenarios, KPI list (placeholder until PDR), reference building cases |
| `api/provider.py` | `MockProvider`: synthetic, deterministic values + synthetic EPW. Replace with a `DatabaseProvider` with the same methods |
| `api/main.py` | FastAPI endpoints = data contract between WP2/WP3 and the interfaces |
| `web/expert/` | Expert map site: selectors, fixed-scale map, location panel, trend chart, EPW download, local results viewer |
| `web/kiosk/` | Kiosk: attract → place → prediction quiz → today vs 2040s → building no action vs adaptation → QR |
| `web/data/units.geojson` | Spatial units for the mock (Italian provinces, ISTAT via openpolis, CC-BY); real units decided at PDR |
| `web/vendor/` | MapLibre GL 4.7.1 and qrcode-generator, stored locally so the kiosk works offline |
| `sim/wedo_sim.py` | Local runner: downloads the EPW, runs EnergyPlus on the expert's PC, writes `wedo_results.json` |
| `sim/tests/fake_energyplus.py` | Stand-in for EnergyPlus, used only to test the runner without EnergyPlus |

## Local simulation (expert)

```bash
python sim/wedo_sim.py check                         # EnergyPlus found? CPUs, RAM, disk
python sim/wedo_sim.py run --idf building.idf --server http://localhost:8000 \
       --unit 001 --period 2011-2020 --scenario historical --period 2041-2050 --scenario rcp85
python sim/wedo_sim.py bench --idf building.idf --epw file.epw --repeat 3   # compute bounds
```

The IDF is copied, the required outputs are appended (SQLite, heating/cooling meters, operative temperature),
EnergyPlus runs locally and the KPIs are read from `eplusout.sql`. The website reads the results file in the
browser: nothing is uploaded.

Test without EnergyPlus: `ENERGYPLUS_EXE=sim/tests/fake_energyplus.py python sim/wedo_sim.py run ...`

## Git rules

- Never commit climate data, EPW outputs or the Python environment (see `.gitignore`).
- Third-party licences: `THIRD_PARTY.md`.

## Known limitations

- All climate values and EPW files are synthetic. Do not use them for design.
- The runner was tested with the fake EnergyPlus only: test it with a real installation and the supervisor's IDF.
- Building-KPI definitions (26 °C threshold, meters used) are placeholders until WP3 fixes them.
- The basemap (OpenFreeMap) is optional; without internet the map shows the units only.
