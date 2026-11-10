#!/usr/bin/env python3
"""We DO local simulation runner (prototype).

Runs the expert's own EnergyPlus model (IDF) on THEIR computer with a We DO weather file,
then extracts building KPIs into a small JSON file that the We DO website can display.
The IDF never leaves the computer: only the EPW is downloaded from the server.

Requirements: Python 3.9+ (standard library only) and EnergyPlus installed locally.

Commands
  check   show EnergyPlus version and machine resources
  run     simulate one IDF with one or more climate cases (period x scenario)
  bench   repeat a simulation to measure run time and memory (client-side compute bounds)

Examples
  python wedo_sim.py check
  python wedo_sim.py run --idf flat.idf --server https://wedo.example.it --unit 001 \
         --period 2041-2050 --scenario rcp85 --period 2011-2020 --scenario historical
  python wedo_sim.py run --idf flat.idf --epw my_weather.epw
  python wedo_sim.py bench --idf flat.idf --epw my_weather.epw --repeat 3
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA = "wedo-results/1"
OVERHEAT_T = 26.0  # °C operative temperature; placeholder until the building-KPI definitions (WP3, Tala) are fixed

KPI_DEFINITIONS = [
    {"code": "heating_need", "name": "Heating need", "unit": "kWh/m²·yr"},
    {"code": "cooling_need", "name": "Cooling need", "unit": "kWh/m²·yr"},
    {"code": "overheat_hours", "name": f"Hours above {OVERHEAT_T:.0f} °C (worst zone)", "unit": "h/yr"},
    {"code": "peak_cooling", "name": "Peak cooling load", "unit": "W/m²"},
]

# Outputs the runner needs; appended to a COPY of the IDF (the original file is never modified).
INJECTED_OUTPUTS = """
! ---- added by wedo_sim.py ----
Output:SQLite, SimpleAndTabular;
Output:Meter, Heating:EnergyTransfer, Hourly;
Output:Meter, Cooling:EnergyTransfer, Hourly;
Output:Variable, *, Zone Operative Temperature, Hourly;
"""


# --------------------------------------------------------------------------- machine & EnergyPlus
def find_energyplus() -> str | None:
    """Find the EnergyPlus executable: ENERGYPLUS_EXE, PATH, then default install folders."""
    env = os.environ.get("ENERGYPLUS_EXE")
    if env and Path(env).exists():
        return env
    for name in ("energyplus", "EnergyPlus", "energyplus.exe"):
        p = shutil.which(name)
        if p:
            return p
    patterns = [r"C:\EnergyPlusV*\energyplus.exe", "/Applications/EnergyPlus-*/energyplus",
                "/usr/local/EnergyPlus-*/energyplus", "/usr/local/bin/energyplus"]
    hits = sorted(h for pat in patterns for h in glob.glob(pat))
    return hits[-1] if hits else None


def energyplus_version(exe: str) -> str:
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        return m.group(1) if m else out.strip()
    except Exception as e:  # noqa: BLE001
        return f"unknown ({e})"


def total_ram_gb() -> float | None:
    try:
        if sys.platform.startswith("win"):
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                            ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            ms = MS(); ms.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return round(ms.total / 1e9, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
    except Exception:  # noqa: BLE001
        return None


def machine_info() -> dict:
    return {"os": f"{platform.system()} {platform.release()}", "cpus": os.cpu_count(),
            "ram_gb": total_ram_gb(), "python": platform.python_version(),
            "disk_free_gb": round(shutil.disk_usage(tempfile.gettempdir()).free / 1e9, 1)}


# --------------------------------------------------------------------------- IDF handling
def idf_version(text: str) -> str | None:
    m = re.search(r"^\s*Version\s*,\s*([\d.]+)\s*;", text, re.IGNORECASE | re.MULTILINE)
    return m.group(1) if m else None


def prepare_idf(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"^\s*RunPeriod\s*,", text, re.IGNORECASE | re.MULTILINE):
        print("  ! warning: no RunPeriod object found; EnergyPlus may only run design days", file=sys.stderr)
    # avoid duplicate Output:SQLite objects (EnergyPlus allows only one)
    text = re.sub(r"^\s*Output:SQLite\s*,[^;]*;", "", text, flags=re.IGNORECASE | re.MULTILINE)
    dst.write_text(text + INJECTED_OUTPUTS, encoding="utf-8")


# --------------------------------------------------------------------------- weather
def fetch_epw(server: str, unit: str, period: str, scenario: str, dst: Path) -> None:
    q = urllib.parse.urlencode({"period": period, "scenario": scenario})
    url = f"{server.rstrip('/')}/api/units/{urllib.parse.quote(unit)}/epw?{q}"
    with urllib.request.urlopen(url, timeout=60) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)
    head = dst.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    if not head or not head[0].startswith("LOCATION"):
        raise RuntimeError(f"downloaded file is not an EPW: {url}")


# --------------------------------------------------------------------------- results
def parse_sql(sql_path: Path) -> dict:
    """Extract KPIs from EnergyPlus' eplusout.sql (Output:SQLite)."""
    con = sqlite3.connect(sql_path)
    cur = con.cursor()

    def series(name: str, is_meter: int) -> dict[str, list[float]]:
        rows = cur.execute(
            """SELECT d.KeyValue, r.Value FROM ReportData r
               JOIN ReportDataDictionary d ON r.ReportDataDictionaryIndex = d.ReportDataDictionaryIndex
               JOIN Time t ON r.TimeIndex = t.TimeIndex
               WHERE d.Name = ? AND d.IsMeter = ? AND d.ReportingFrequency = 'Hourly'
                 AND (t.WarmupFlag IS NULL OR t.WarmupFlag = 0)
               ORDER BY r.TimeIndex""", (name, is_meter)).fetchall()
        out: dict[str, list[float]] = {}
        for key, val in rows:
            out.setdefault(key or "", []).append(val)
        return out

    area = cur.execute(
        """SELECT Value FROM TabularDataWithStrings WHERE ReportName='AnnualBuildingUtilityPerformanceSummary'
           AND TableName='Building Area' AND RowName='Total Building Area' AND ColumnName='Area'""").fetchone()
    area_m2 = float(area[0]) if area and str(area[0]).strip() else None
    heat = sum(sum(v) for v in series("Heating:EnergyTransfer", 1).values())     # J
    cool_series = series("Cooling:EnergyTransfer", 1)
    cool = sum(sum(v) for v in cool_series.values())
    peak_cool_w = max((max(v) / 3600 for v in cool_series.values() if v), default=0.0)  # J per hour -> W
    temps = series("Zone Operative Temperature", 0)
    hours_by_zone = {z: sum(1 for t in v if t > OVERHEAT_T) for z, v in temps.items()}
    con.close()
    per_m2 = (lambda x: round(x / area_m2, 1)) if area_m2 else (lambda x: None)
    return {
        "floor_area_m2": area_m2,
        "kpis": {"heating_need": per_m2(heat / 3.6e6), "cooling_need": per_m2(cool / 3.6e6),
                 "overheat_hours": max(hours_by_zone.values(), default=0),
                 "peak_cooling": per_m2(peak_cool_w)},
        "overheat_hours_by_zone": hours_by_zone,
    }


# --------------------------------------------------------------------------- simulation
def simulate(exe: str, idf: Path, epw: Path, workdir: Path) -> dict:
    workdir.mkdir(parents=True, exist_ok=True)
    prepared = workdir / "model_wedo.idf"
    prepare_idf(idf, prepared)
    cmd = [exe, "--weather", str(epw), "--output-directory", str(workdir), "--readvars", str(prepared)]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    runtime = time.perf_counter() - t0
    err_file = workdir / "eplusout.err"
    err_text = err_file.read_text(errors="replace") if err_file.exists() else ""
    severe = len(re.findall(r"\*\* Severe  \*\*", err_text))
    fatal = "**  Fatal  **" in err_text or proc.returncode != 0
    res = {"runtime_s": round(runtime, 1), "returncode": proc.returncode, "severe_errors": severe,
           "ok": not fatal and (workdir / "eplusout.sql").exists(),
           "output_mb": round(sum(f.stat().st_size for f in workdir.glob("*")) / 1e6, 1)}
    if res["ok"]:
        res.update(parse_sql(workdir / "eplusout.sql"))
    else:
        res["error"] = (err_text[-1500:] or proc.stderr[-1500:]).strip()
    return res


def _cases(args) -> list[dict]:
    if args.epw:
        return [{"label": Path(args.epw).stem, "epw": Path(args.epw)}]
    periods, scenarios = args.period or [], args.scenario or []
    if not (args.server and args.unit and periods):
        sys.exit("give --epw FILE, or --server URL --unit ID --period P [--scenario S] (repeatable)")
    if len(scenarios) not in (0, 1, len(periods)):
        sys.exit("give one --scenario, or one per --period")
    scenarios = scenarios * len(periods) if len(scenarios) <= 1 else scenarios
    scenarios = [s or "historical" for s in (scenarios or ["historical"] * len(periods))]
    return [{"label": f"{p} {s}", "period": p, "scenario": s} for p, s in zip(periods, scenarios)]


def cmd_check(_args) -> None:
    exe = find_energyplus()
    info = machine_info()
    print(json.dumps({"energyplus": exe, "version": energyplus_version(exe) if exe else None, **info}, indent=2))
    if not exe:
        print("EnergyPlus not found: install it or set ENERGYPLUS_EXE", file=sys.stderr)
        sys.exit(1)


def cmd_run(args) -> None:
    exe = find_energyplus() or sys.exit("EnergyPlus not found: install it or set ENERGYPLUS_EXE")
    idf = Path(args.idf).resolve()
    ep_ver = energyplus_version(exe)
    v = idf_version(idf.read_text(encoding="utf-8", errors="replace"))
    if v and not ep_ver.startswith(v.rsplit(".", 1)[0] if v.count(".") >= 2 else v):
        print(f"  ! IDF version {v} differs from EnergyPlus {ep_ver}: run IDFVersionUpdater first", file=sys.stderr)
    out_dir = Path(args.out).resolve()
    cases = _cases(args)
    for c in cases:                                   # download weather files first (sequential, small)
        if "epw" not in c:
            c["epw"] = out_dir / f"{args.unit}_{c['period']}_{c['scenario']}.epw"
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"downloading EPW {c['label']} …")
            fetch_epw(args.server, args.unit, c["period"], c["scenario"], c["epw"])
    workers = max(1, min(len(cases), args.jobs or max(1, (os.cpu_count() or 2) - 1)))
    print(f"running {len(cases)} simulation(s) with {workers} parallel job(s) …")
    with cf.ThreadPoolExecutor(workers) as pool:
        futs = {pool.submit(simulate, exe, idf, c["epw"], out_dir / re.sub(r"\W+", "_", c["label"])): c for c in cases}
        for f in cf.as_completed(futs):
            c = futs[f]; c.update(f.result())
            print(f"  {c['label']}: {'ok' if c['ok'] else 'FAILED'} in {c['runtime_s']} s")
    area = next((c.get("floor_area_m2") for c in cases if c.get("floor_area_m2")), None)
    report = {
        "schema": SCHEMA, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": {"file": idf.name, "sha256": hashlib.sha256(idf.read_bytes()).hexdigest()[:16], "floor_area_m2": area},
        "energyplus": {"version": ep_ver}, "machine": machine_info(), "kpi_definitions": KPI_DEFINITIONS,
        "cases": [{k: (str(v) if isinstance(v, Path) else v) for k, v in c.items() if k != "epw"} for c in cases],
    }
    dst = out_dir / "wedo_results.json"
    dst.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nresults: {dst}\nopen the We DO website > your place > 'Open the results file' to view them.")


def cmd_bench(args) -> None:
    """Measure run time and peak memory to define the client-side compute bounds (PDR action 3)."""
    exe = find_energyplus() or sys.exit("EnergyPlus not found: install it or set ENERGYPLUS_EXE")
    idf, epw = Path(args.idf).resolve(), Path(args.epw).resolve()
    runs = []
    for i in range(args.repeat):
        with tempfile.TemporaryDirectory() as tmp:
            r = simulate(exe, idf, epw, Path(tmp))
        try:
            import resource  # unix only: peak RSS of child processes
            peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            peak_mb = round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 0)
        except ImportError:
            peak_mb = None
        runs.append({"run": i + 1, "runtime_s": r["runtime_s"], "ok": r["ok"], "output_mb": r["output_mb"],
                     "peak_memory_mb": peak_mb})
        print(f"  run {i + 1}: {r['runtime_s']} s, ok={r['ok']}")
    times = [r["runtime_s"] for r in runs if r["ok"]]
    report = {"model": idf.name, "energyplus": energyplus_version(exe), "machine": machine_info(), "runs": runs,
              "median_runtime_s": sorted(times)[len(times) // 2] if times else None}
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="show EnergyPlus and machine info").set_defaults(fn=cmd_check)
    r = sub.add_parser("run", help="simulate an IDF with We DO weather files")
    r.add_argument("--idf", required=True)
    r.add_argument("--epw", help="use a local EPW instead of downloading one")
    r.add_argument("--server", help="We DO server, e.g. https://wedo.example.it")
    r.add_argument("--unit", help="location id shown on the website")
    r.add_argument("--period", action="append", help="e.g. 2041-2050 (repeatable)")
    r.add_argument("--scenario", action="append", help="historical | rcp45 | rcp85 (repeatable)")
    r.add_argument("--out", default="wedo_out")
    r.add_argument("--jobs", type=int, help="parallel simulations (default: CPUs - 1)")
    r.set_defaults(fn=cmd_run)
    b = sub.add_parser("bench", help="measure run time to set compute bounds")
    b.add_argument("--idf", required=True); b.add_argument("--epw", required=True)
    b.add_argument("--repeat", type=int, default=3); b.add_argument("--out", default="wedo_bench.json")
    b.set_defaults(fn=cmd_bench)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
