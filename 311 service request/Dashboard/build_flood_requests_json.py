#!/usr/bin/env python3
"""Summarise finished flooding requests into one small JSON file for the web app.

The web page cannot read the yearly 311 CSV files (about 475 MB). This script
reads them once, counts requests per ward, year, season and request type, and
writes web/public/flood_requests.json.

Which requests count is decided by plot_flood_requests_by_season.py
(load_requests): only the request types in 311_SR_label_to_keep.csv, and only
finished requests (Closed before 2022, Completed from 2022). This script reuses
that function so the notebook charts and the web charts always agree.

That script imports matplotlib, so matplotlib must be installed
(it is in requirements.txt).

    python "311 service request/Dashboard/build_flood_requests_json.py"

Shape of the JSON:

    "wards": {"1": [year][season][type], ...}

where year follows "years", season follows "seasons" and type follows "types".
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import plot_flood_requests_by_season as plots  # noqa: E402

FIRST_YEAR = 2019
LAST_YEAR = 2026
WARD_IDS = list(range(1, 26))


def build_payload(requests, request_types):
    """Count requests per ward, year, season and type.

    `requests` is the frame returned by load_requests: it has the columns
    Creation Date, Ward, Service Request Type and season.
    """
    frame = requests.copy()
    frame["ward_id"] = frame["Ward"].map(plots.ward_number)
    frame["year"] = pd.to_datetime(frame["Creation Date"]).dt.year
    years = list(range(int(frame["year"].min()), int(frame["year"].max()) + 1))
    seasons = list(plots.SEASONS)

    counts = frame.groupby(["ward_id", "year", "season", "Service Request Type"]).size()
    wards = {}
    for ward_id in sorted(frame["ward_id"].unique()):
        table = [[[0] * len(request_types) for _ in seasons] for _ in years]
        for (year, season, request_type), n in counts.loc[ward_id].items():
            table[years.index(year)][seasons.index(season)][request_types.index(request_type)] = int(n)
        wards[str(int(ward_id))] = table

    return {
        "years": years,
        "seasons": seasons,
        "types": list(request_types),
        "total": int(len(frame)),
        "wards": wards,
    }


def check(payload):
    """Stop with a clear message if the counts do not add up."""
    ids = sorted(int(key) for key in payload["wards"])
    if ids != WARD_IDS:
        raise SystemExit(f"Expected wards 1 to 25, found {ids}")
    counted = sum(
        n
        for table in payload["wards"].values()
        for year in table
        for season in year
        for n in season
    )
    if counted != payload["total"]:
        raise SystemExit(f"Counts add up to {counted}, but the total is {payload['total']}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "web" / "public" / "flood_requests.json",
        help="Where to write the JSON.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    paths = [HERE / f"SR{year}.csv" for year in range(FIRST_YEAR, LAST_YEAR + 1)]
    labels = HERE / "311_SR_label_to_keep.csv"
    requests, request_types = plots.load_requests(paths, labels)

    payload = build_payload(requests, request_types)
    check(payload)

    # The newest request in the last file, so the page can say where the data stops.
    latest = plots.read_requests(paths[-1])["Creation Date"].max()
    payload = {
        "source": "City of Toronto 311 service requests",
        "filter": "Finished requests only (Closed before 2022, Completed from 2022)",
        "through": str(latest)[:10],
        **payload,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{payload['total']:,} finished flooding requests, {len(payload['wards'])} wards, through {payload['through']}")
    print(f"Wrote {args.output} ({args.output.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
