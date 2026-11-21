#!/usr/bin/env python3
"""Stacked seasonal counts of finished flooding requests, one panel per ward.

Loads one or more yearly 311 extracts, keeps the service types in
311_SR_label_to_keep.csv, and writes a PNG. Status is "Closed" before
2022 and "Completed" from 2022 on.

Winter is December–February, spring March–May, summer June–August,
and fall September–November. December is grouped with January and
February of the same file year.

Example:
    python3 plot_flood_requests_by_season.py SR2019.csv SR2020.csv
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

SEASON_BY_MONTH = {
    12: "Winter",
    1: "Winter",
    2: "Winter",
    3: "Spring",
    4: "Spring",
    5: "Spring",
    6: "Summer",
    7: "Summer",
    8: "Summer",
    9: "Fall",
    10: "Fall",
    11: "Fall",
}
SEASONS = ["Winter", "Spring", "Summer", "Fall"]
COLORS = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2"]
REQUEST_COLUMNS = ["Creation Date", "Status", "Ward", "Service Request Type"]


def parse_args():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Yearly 311 CSV files. Defaults to SR2019.csv and SR2020.csv beside this script.",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=here / "311_SR_label_to_keep.csv",
        help="CSV of service request types to keep.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("flood_requests_by_season.png"),
        help="Where to write the chart.",
    )
    parser.add_argument(
        "--by-year",
        action="store_true",
        help="Draw one chart per ward, with a bar for each season of each year.",
    )
    args = parser.parse_args()
    if not args.files:
        args.files = [here / "SR2019.csv", here / "SR2020.csv"]
    return args


def ward_number(name):
    return int(name.rsplit("(", 1)[1].rstrip(")"))


def read_requests(path):
    # SR2025.csv is Windows-1252 (for example "Café"); the earlier files are UTF-8.
    for encoding in ("utf-8", "cp1252"):
        try:
            return pd.read_csv(path, usecols=REQUEST_COLUMNS, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"Could not read {path} as UTF-8 or Windows-1252.")


def load_requests(paths, labels_path):
    missing = [path for path in [labels_path, *paths] if not path.exists()]
    if missing:
        names = ", ".join(str(path) for path in missing)
        raise SystemExit(f"File not found: {names}")

    labels = pd.read_csv(labels_path)
    request_types = labels["Service type to keep"].tolist()
    frames = [read_requests(path) for path in paths]
    requests = pd.concat(frames, ignore_index=True)
    created = pd.to_datetime(requests["Creation Date"])
    # 311 renamed the finished status from Closed to Completed in 2022.
    finished = (
        ((created.dt.year < 2022) & (requests["Status"] == "Closed"))
        | ((created.dt.year >= 2022) & (requests["Status"] == "Completed"))
    )
    requests = requests[
        requests["Service Request Type"].isin(request_types) & finished
    ].copy()
    if requests.empty:
        raise SystemExit("No finished requests matched the label list.")

    created = pd.to_datetime(requests["Creation Date"])
    requests["month"] = created.dt.month
    requests["season"] = requests["month"].map(SEASON_BY_MONTH)
    return requests, request_types


def plot_seasons(requests, request_types, output):
    season_counts = (
        requests.groupby(["Ward", "season", "Service Request Type"])
        .size()
        .unstack("Service Request Type", fill_value=0)
        .reindex(columns=request_types, fill_value=0)
    )
    wards = sorted(requests["Ward"].dropna().unique(), key=ward_number)

    fig, axes = plt.subplots(5, 5, figsize=(18, 16), sharex=True, sharey=True)
    axes = axes.ravel()

    for ax, ward in zip(axes, wards):
        ward_counts = season_counts.loc[ward].reindex(SEASONS, fill_value=0)
        bottom = None
        for request_type, color in zip(request_types, COLORS):
            values = ward_counts[request_type].to_numpy()
            ax.bar(
                SEASONS,
                values,
                bottom=0 if bottom is None else bottom,
                color=color,
                width=0.7,
                label=request_type,
            )
            bottom = values if bottom is None else bottom + values
        ax.set_title(ward, fontsize=8)

    for ax in axes[len(wards) :]:
        ax.axis("off")

    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        legend_labels,
        loc="upper center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 1.02),
    )
    fig.suptitle("Finished flooding requests by ward and season", y=1.06)
    fig.supxlabel("Season")
    fig.supylabel("Number of requests")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)


SEASON_TICKS = ["W", "Sp", "Su", "F"]


def plot_seasons_by_year(requests, request_types, output):
    requests = requests.copy()
    requests["year"] = pd.to_datetime(requests["Creation Date"]).dt.year
    years = list(range(int(requests["year"].min()), int(requests["year"].max()) + 1))
    counts = (
        requests.groupby(["Ward", "year", "season", "Service Request Type"])
        .size()
        .unstack("Service Request Type", fill_value=0)
        .reindex(columns=request_types, fill_value=0)
    )
    slots = pd.MultiIndex.from_product([years, SEASONS], names=["year", "season"])
    wards = sorted(requests["Ward"].dropna().unique(), key=ward_number)
    x = list(range(len(slots)))

    fig, axes = plt.subplots(
        len(wards),
        1,
        figsize=(16, 2.3 * len(wards)),
        sharex=True,
        sharey=True,
    )

    for ax, ward in zip(axes, wards):
        ward_counts = counts.loc[ward].reindex(slots, fill_value=0)
        bottom = None
        for request_type, color in zip(request_types, COLORS):
            values = ward_counts[request_type].to_numpy()
            ax.bar(
                x,
                values,
                bottom=0 if bottom is None else bottom,
                color=color,
                width=0.85,
                label=request_type,
            )
            bottom = values if bottom is None else bottom + values
        ax.set_title(ward, loc="left", fontsize=10)
        for year_index in range(1, len(years)):
            ax.axvline(year_index * len(SEASONS) - 0.5, color="0.75", linewidth=0.8)

    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(SEASON_TICKS * len(years))
    axes[-1].set_xlabel("Season")
    for year_index, year in enumerate(years):
        axes[-1].text(
            year_index * len(SEASONS) + (len(SEASONS) - 1) / 2,
            -0.55,
            str(year),
            ha="center",
            va="top",
            transform=axes[-1].get_xaxis_transform(),
            fontsize=9,
            clip_on=False,
        )

    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        legend_labels,
        loc="upper center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 1.005),
    )
    fig.suptitle("Finished flooding requests by ward, season, and year", y=1.02)
    fig.supylabel("Number of requests")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=120, bbox_inches="tight")
    plt.close(fig)


def main():
    args = parse_args()
    requests, request_types = load_requests(args.files, args.labels)
    if args.by_year:
        plot_seasons_by_year(requests, request_types, args.output)
    else:
        plot_seasons(requests, request_types, args.output)
    sources = ", ".join(path.name for path in args.files)
    print(f"{len(requests):,} finished flooding requests from {sources}")
    print(f"Saved {args.output.resolve()}")


if __name__ == "__main__":
    main()
