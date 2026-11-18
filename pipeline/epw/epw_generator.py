"""WeDO EPW generator v0.1 (Python 3.10+, standard library only).

This is a *format converter*, not a weather downscaling or solar-radiation model.
It accepts a CSV with all 35 EPW data fields and writes an EPW with eight
header records copied from a verified, site-matched template EPW.

Usage:
    python epw_generator.py inspect --epw Torino_IT-hour.epw
    python epw_generator.py export-csv --epw Torino_IT-hour.epw --csv torino_input.csv
    python epw_generator.py build --csv torino_input.csv --template Torino_IT-hour.epw --output torino_test.epw
    python epw_generator.py inspect --epw torino_test.epw
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

FIELDS = [
    "year", "month", "day", "hour", "minute", "data_source_flags",
    "dry_bulb_C", "dew_point_C", "relative_humidity_pct", "pressure_Pa",
    "extraterrestrial_horizontal_Wm2", "extraterrestrial_direct_normal_Wm2",
    "horizontal_infrared_Wm2", "ghi_Wm2", "dni_Wm2", "dhi_Wm2",
    "global_horizontal_illuminance_lux", "direct_normal_illuminance_lux",
    "diffuse_horizontal_illuminance_lux", "zenith_luminance_cdm2",
    "wind_direction_deg", "wind_speed_ms", "total_sky_cover_tenths",
    "opaque_sky_cover_tenths", "visibility_km", "ceiling_height_m",
    "present_weather_observation", "present_weather_codes",
    "precipitable_water_mm", "aerosol_optical_depth", "snow_depth_cm",
    "days_since_last_snowfall", "albedo", "liquid_precipitation_mm",
    "liquid_precipitation_quantity_hr",
]
HEADERS = [
    "LOCATION", "DESIGN CONDITIONS", "TYPICAL/EXTREME PERIODS",
    "GROUND TEMPERATURES", "HOLIDAYS/DAYLIGHT SAVINGS", "COMMENTS 1",
    "COMMENTS 2", "DATA PERIODS",
]
NUMERIC = [i for i in range(35) if i not in (5, 26, 27)]
MISSING_LIMIT = {
    6: 99.9, 7: 99.9, 8: 999, 9: 999999, 13: 9999,
    14: 9999, 15: 9999, 20: 999, 21: 999,
}


def read_epw(path: Path) -> tuple[list[list[str]], list[list[str]]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        records = list(csv.reader(stream))
    if len(records) < 9:
        raise ValueError("EPW needs 8 header lines and at least 1 weather record")
    headers, data = records[:8], records[8:]
    if [r[0].strip().upper() if r else "" for r in headers] != HEADERS:
        raise ValueError("EPW header names/order incorrect")
    return headers, data


def validate(rows: list[list[str]], require_full_year: bool = True) -> None:
    if require_full_year and len(rows) != 8760:
        raise ValueError(f"Expected 8760 hourly records, found {len(rows)}")
    previous = None
    years = set()
    for number, row in enumerate(rows, 1):
        if len(row) != 35:
            raise ValueError(f"Data row {number}: expected 35 fields, got {len(row)}")
        try:
            yy, mm, dd, hh, minute = (int(row[i]) for i in range(5))
            day = date(yy, mm, dd)
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Data row {number}: invalid date/time") from exc
        if hh not in range(1, 25) or minute != 60:
            raise ValueError(f"Data row {number}: expected EPW hour 1..24, minute 60")
        key = (day.toordinal() * 24 + hh - 1)
        if previous is not None and key != previous + 1:
            raise ValueError(f"Data row {number}: duplicate or nonconsecutive hour")
        previous = key
        years.add(yy)
        for i in NUMERIC:
            try:
                value = float(row[i])
            except ValueError as exc:
                raise ValueError(f"Data row {number}: {FIELDS[i]} is not numeric") from exc
            if value != value or value in (float('inf'), float('-inf')):
                raise ValueError(f"Data row {number}: {FIELDS[i]} is not finite")
            if i in MISSING_LIMIT and value >= MISSING_LIMIT[i]:
                raise ValueError(f"Data row {number}: missing/sentinel value in {FIELDS[i]}")
        dry, dew, rh, pressure = (float(row[i]) for i in (6, 7, 8, 9))
        if dew > dry + 0.15 or not 0 <= rh <= 100 or not 50000 <= pressure <= 120000:
            raise ValueError(f"Data row {number}: inconsistent temperature/humidity/pressure")
        if any(float(row[i]) < 0 for i in (13, 14, 15, 21)):
            raise ValueError(f"Data row {number}: negative radiation or wind speed")
        if not 0 <= float(row[20]) <= 360:
            raise ValueError(f"Data row {number}: invalid wind direction")
    if require_full_year:
        if len(years) != 1:
            raise ValueError("Starter version supports one calendar year per EPW only")
        year = next(iter(years))
        if date(year, 12, 31).timetuple().tm_yday != 365:
            raise ValueError("Starter version requires a non-leap year (8760 hours)")
        if int(rows[0][1]) != 1 or int(rows[0][2]) != 1 or int(rows[0][3]) != 1:
            raise ValueError("Year must begin Jan 1, hour 1")
        if int(rows[-1][1]) != 12 or int(rows[-1][2]) != 31 or int(rows[-1][3]) != 24:
            raise ValueError("Year must end Dec 31, hour 24")


def export_csv(epw_path: Path, csv_path: Path) -> None:
    _, data = read_epw(epw_path)
    validate(data)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        writer.writerows(data)


def build(csv_path: Path, template_path: Path, output_path: Path) -> None:
    if output_path.resolve() in (csv_path.resolve(), template_path.resolve()):
        raise ValueError("Output must not overwrite input or template")
    template_header, _ = read_epw(template_path)
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise ValueError("CSV column names/order must match FIELDS in epw_generator.py")
        rows = [[record[name].strip() for name in FIELDS] for record in reader]
    validate(rows)
    # Template metadata must be appropriate for this station/location. Update
    # LOCATION and DATA PERIODS only after confirming coordinates and period.
    header = [record.copy() for record in template_header]
    year = rows[0][0]
    header[6] = ["COMMENTS 2", f"WeDO v0.1; converted from {csv_path.name}; calendar year {year}; verify climate provenance"]
    # No silent location, scenario, or radiation synthesis.
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerows(header)
        writer.writerows(rows)
    _, written = read_epw(output_path)
    validate(written)
    print(f"Created {output_path} with {len(written)} hourly records")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("inspect")
    check.add_argument("--epw", type=Path, required=True)
    export = commands.add_parser("export-csv")
    export.add_argument("--epw", type=Path, required=True)
    export.add_argument("--csv", type=Path, required=True)
    generate = commands.add_parser("build")
    generate.add_argument("--csv", type=Path, required=True)
    generate.add_argument("--template", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "inspect":
        headers, rows = read_epw(args.epw)
        validate(rows)
        print(f"PASS: {len(rows)} records, 35 fields, 8 headers; location={headers[0][1]}")
    elif args.command == "export-csv":
        export_csv(args.epw, args.csv)
        print(f"Exported {args.csv}")
    else:
        build(args.csv, args.template, args.output)


if __name__ == "__main__":
    main()
