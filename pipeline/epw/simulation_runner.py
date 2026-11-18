"""WeDO PDR: automated local EnergyPlus run using an IDF and one or more EPWs.

No Python dependencies. Does not change the supplied IDF or EPW.

Examples (Windows PowerShell):
  python simulation_runner.py --idf "test(1).idf" --epw Torino_IT-hour.epw --dry-run
  python simulation_runner.py --idf "test(1).idf" --epw Torino_IT-hour.epw --energyplus "C:\\EnergyPlusV9-6-0\\energyplus.exe"

Output: one isolated directory per EPW, with EnergyPlus outputs, execution.log,
and simulation_report.json. Batch runs: supply --epw multiple times.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def idf_version(path: Path) -> str | None:
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    content = re.sub(r"![^\n]*", "", content)
    match = re.search(r"\bVersion\s*,\s*([0-9]+(?:\.[0-9]+){1,2})\s*;", content, re.I)
    return match.group(1) if match else None


def epw_info(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if not header or header[0].upper() != "LOCATION" or len(header) < 10:
            raise ValueError(f"Invalid EPW LOCATION header: {path}")
        for _ in range(7):
            if next(reader, None) is None:
                raise ValueError(f"Missing EPW header records in {path}")
        count = 0
        for row in reader:
            count += 1
            if len(row) != 35:
                raise ValueError(f"EPW row {count} has {len(row)} fields, expected 35")
    if count != 8760:
        raise ValueError(f"EPW has {count} records; PDR runner expects a 8760-hour year")
    return {
        "city": header[1], "latitude": float(header[6]),
        "longitude": float(header[7]), "time_zone": float(header[8]),
        "elevation_m": float(header[9]), "hourly_records": count,
    }


def find_executable(value: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    located = shutil.which(value)
    if not located:
        raise FileNotFoundError(
            "EnergyPlus executable not found. Install EnergyPlus matching your IDF "
            "and pass --energyplus PATH_TO_energyplus.exe (or put it on PATH)."
        )
    return Path(located).resolve()


def get_version(exe: Path) -> str:
    result = subprocess.run([str(exe), "--version"], capture_output=True,
                            text=True, timeout=30, check=False)
    return (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr).strip() else "unknown"


def parse_error_log(path: Path) -> dict:
    if not path.is_file():
        return {"present": False, "severe_count": None, "fatal_count": None, "summary": "Missing .err file"}
    content = path.read_text(encoding="utf-8", errors="replace")
    # Count the individual error messages, not both messages and summary lines.
    severe = len(re.findall(r"\*\*\s*Severe\s*\*\*", content, re.I))
    fatal = len(re.findall(r"\*\*\s*Fatal\s*\*\*", content, re.I))
    lines = [line.strip() for line in content.splitlines() if "EnergyPlus Completed" in line]
    return {"present": True, "severe_count": severe, "fatal_count": fatal,
            "summary": lines[-1] if lines else "No completion summary found"}


def run_one(exe: Path | None, idf: Path, epw: Path, output_root: Path,
            timeout_seconds: int, dry_run: bool) -> dict:
    info = epw_info(epw)
    tag = re.sub(r"[^a-zA-Z0-9_-]+", "_", epw.stem).strip("_")[:65]
    fingerprint = hashlib.sha256(str(epw.resolve()).encode()).hexdigest()[:8]
    output = output_root / f"{tag}_{fingerprint}"
    command = [str(exe) if exe else "energyplus", "-w", str(epw),
               "-d", str(output), "-p", "eplus", "-r", str(idf)]
    report = {
        "status": "dry_run" if dry_run else "not_started",
        "idf": str(idf), "idf_version": idf_version(idf),
        "epw": str(epw), "epw_info": info,
        "energyplus_executable": str(exe) if exe else None,
        "command": command, "output_directory": str(output),
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    if dry_run:
        return report
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing simulation: {output}")
    output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=timeout_seconds, check=False)
        report["return_code"] = completed.returncode
        (output / "execution.log").write_text(
            "COMMAND: " + subprocess.list2cmdline(command) + "\n\nSTDOUT:\n" +
            completed.stdout + "\nSTDERR:\n" + completed.stderr,
            encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        report.update(status="timeout", error=f"Simulation exceeded {timeout_seconds} seconds")
    except OSError as exc:
        report.update(status="execution_error", error=str(exc))
    report["runtime_seconds"] = round(time.monotonic() - start, 2)
    error_report = parse_error_log(output / "eplusout.err")
    report["energyplus_errors"] = error_report
    report["output_files"] = sorted(p.name for p in output.iterdir() if p.is_file())
    if report["status"] == "not_started":
        success = (report.get("return_code") == 0 and error_report["present"]
                   and error_report["fatal_count"] == 0
                   and "Completed Successfully" in error_report["summary"])
        report["status"] = "success" if success else "failed"
    (output / "simulation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["output_files"] = sorted(p.name for p in output.iterdir() if p.is_file())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--idf", type=Path, required=True, help="Reference building IDF")
    parser.add_argument("--epw", type=Path, action="append", required=True,
                        help="Weather file; repeat for multiple simulations")
    parser.add_argument("--energyplus", default="energyplus", help="Executable or full path")
    parser.add_argument("--output-root", type=Path, default=Path("simulation_outputs"))
    parser.add_argument("--timeout", type=int, default=3600, help="Seconds per simulation")
    parser.add_argument("--dry-run", action="store_true", help="Check inputs and preview command without running")
    args = parser.parse_args()
    idf = args.idf.expanduser().resolve()
    if not idf.is_file():
        parser.error(f"IDF not found: {idf}")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    version = idf_version(idf)
    print(f"IDF version: {version or 'unknown'}")
    exe = None if args.dry_run else find_executable(args.energyplus)
    if exe is not None:
        actual = get_version(exe)
        print(f"Installed EnergyPlus: {actual}")
        if version and not re.search(rf"(?<!\d){re.escape(version)}(?:\.\d+)?(?!\d)", actual):
            print("WARNING: IDF/EnergyPlus version may differ; 9.6 IDF usually needs 9.6 or conversion.", file=sys.stderr)
    any_failures = False
    for source in args.epw:
        epw = source.expanduser().resolve()
        if not epw.is_file():
            print(f"ERROR: EPW not found: {epw}", file=sys.stderr)
            any_failures = True
            continue
        try:
            result = run_one(exe, idf, epw, args.output_root.expanduser().resolve(),
                             args.timeout, args.dry_run)
            print(json.dumps({k: result[k] for k in ("status", "epw", "output_directory", "command")}, indent=2))
            if result["status"] not in ("success", "dry_run"):
                any_failures = True
        except (ValueError, OSError) as exc:
            print(f"ERROR: {epw}: {exc}", file=sys.stderr)
            any_failures = True
    return 1 if any_failures else 0


if __name__ == "__main__":
    sys.exit(main())
