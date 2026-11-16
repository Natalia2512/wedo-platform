# Data pipeline (runs on OLGYAY)

One folder per step. Scripts read their settings from `config/` and write to `/data/wedo/` on OLGYAY.
Test on a small sample first (one year, one region), then run the full job inside `tmux`.

| Folder | Step | Output on OLGYAY | Owner (WBS) |
|---|---|---|---|
| `download/` | Download datasets, resume, checksums | `raw/`, `logs/` | Emanuele (2.1.1) |
| `processing/` | Units, local time, derived variables, gaps, QC report | `processed/` | Tala (2.1.2) |
| `processing/` | Bias correction and validation | `validated/` | Emanuele (2.1.3) |
| `epw/` | One EPW per place, decade, scenario | `epw/` | Shiyun (3.2.1) |
| `kpi/` | Climate and virtual-building KPIs | `kpi/` | Zengqi (3.2.2), Tala (3.2.4) |
| `simulation/` | Kiosk precompute: reference building, no action vs adaptation | `kpi/building/` | Shiyun (3.2.3) |
| `release/` | Package and copy a versioned release to the public server | `releases/<version>/` | Zengqi, Natalia (4.3.1) |

Each script should: print what it does, skip work already done (so a rerun resumes), and write a log to `/data/wedo/logs/`.
