# How we work in this repository

The rule is simple: **Git for what we write, OLGYAY for what we download or compute, Teams for what we present.**

## Where things go

| What | Where |
|---|---|
| Scripts (download, processing, EPW, KPIs, simulation, release) | this repo, `pipeline/<step>/` |
| Settings shared by scripts (datasets, area, periods, variables) | this repo, `config/` |
| Interface prototype (API, expert site, kiosk) | this repo, `api/`, `web/` |
| Local simulation runner for experts | this repo, `sim/` |
| Architecture, decisions, guides | this repo, `docs/` |
| Results of every test or trial (sizes, times, errors, conclusions) | this repo, `docs/tests/` – one Markdown file per test, from `TEMPLATE.md` |
| Small sample files for testing (< 5 MB, synthetic or redistributable) | this repo, `samples/` |
| Real climate data, EPW files, KPI tables, logs, checksums | **OLGYAY**, `/data/wedo/` – never in Git |
| Slides, PDFs, meeting notes, screenshots | **Teams** channel files |

Never commit climate data: it is too big for Git, and some datasets (CMCC) do not allow redistribution, even in a private repo.

## Folder layout on OLGYAY

```
/data/wedo/
  raw/<dataset>/<scenario>/<variable>/<year>.nc
  processed/   validated/   epw/   kpi/   releases/<version>/
  logs/        (download logs, checksums, QC reports)
```

## Where scripts run

| Script | Runs on | Why |
|---|---|---|
| `pipeline/download`, `processing`, `epw`, `kpi`, `simulation` (kiosk precompute), `release` | OLGYAY, inside `tmux` | Data is TB-scale and stays there |
| `api/`, `web/` (prototype) | your laptop, for development | Small and uses mock data |
| `sim/wedo_sim.py` | the expert's laptop (yours for testing) | Building models stay on the user's computer |

Develop and test a script on a small sample (one year, one region) on your laptop or on OLGYAY, then run the full job on OLGYAY.

## Working with Git

1. Before you start: **Pull** (GitHub Desktop: *Fetch origin* → *Pull*).
2. Work on your own branch: `<name>/<topic>`, e.g. `emanuele/download-era5`.
3. Commit small steps with clear messages: `download: add ERA5 resume and checksums`.
4. Open a **Pull Request** to `main`; your backup in the WBS reviews it.
5. Never commit: data, `.env` files, passwords, API keys (`~/.cdsapirc` stays on OLGYAY).

## After every test or trial

1. Copy `docs/tests/TEMPLATE.md` to `docs/tests/T<n>_<short-name>.md` and fill it in.
2. Add a line to the table in `docs/tests/README.md`.
3. If you measured a number used in the architecture (size, time, count), tell Natalia, or update the Assumptions panel in `docs/architecture.html`.
