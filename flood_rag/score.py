"""Transparent ward index. The ranking is arithmetic, not a language model.

Question this score answers
---------------------------
Which wards combine high sewage-failure pressure with low basement-flood
reporting (2019-2022), and which of those also have low Basement Flooding
Protection subsidy uptake as of the June 2025 ward profiles.

Windows
-------
- 311 complaint rates in the score: 2019-2021 mean only. The local 2022 extract
  collapses to a few calls per ward, so it is a partial year. Yearly counts and
  rates for 2019-2022 are kept as attributes and are not folded into the mean.
- Residential water use in the score: 2019-2022 mean. Each year's value is
  also kept as an attribute.
- Basement-flood service requests: 2019-2022 (full years in the City file).
  2023 in that file is January-June only.
- Sewer structure for the historical score: 2021 snapshot.
- 2025 projection: 2023 sewer snapshot, pipe age plus two years, complaint
  rates held at the 2019-2021 mean. Every ward ages together, so age alone
  does not reshuffle the ranking. Recent pipe installation (new_pipe_km) does.
- Subsidy stock: parsed from Attachment 1 (ward profile PDF), June 2025.

Eligible homes are "properties with flood protection" plus "properties
without" on that PDF. That is the City's low-rise subsidy universe
(single-family, duplex, triplex), which is the right denominator for both
backup complaints and flood reports.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from flood_rag.paths import FLOODS, REQUESTS_311, SEWER, TREES, WATER_DIR
from flood_rag.policy import load_subsidy_stock

STRUCTURAL_COLS = [
    "pct_combined_sewer",
    "pct_old_pipe",
    "avg_pipe_age",
    "fd_density",
    "pipe_share_in_root_zone",
    "avg_residential_usage",
]
COMPLAINT_COLS = ["backup_per_1000", "manhole_per_1000"]
CALL_SCORE_YEARS = (2019, 2020, 2021)
CALL_SERIES_YEARS = (2019, 2020, 2021, 2022)
WATER_YEARS = (2019, 2020, 2021, 2022)
CALL_SERIES_COLS = ("sewer_backup", "manhole_overflow", "catch_basin")


def _z(series: pd.Series) -> pd.Series:
    std = float(series.std(ddof=0))
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def _load_311() -> pd.DataFrame:
    frame = pd.read_csv(REQUESTS_311)
    frame["ward_id"] = frame["Ward"].str.extract(r"\((\d+)\)").astype(int)
    frame = frame.rename(
        columns={
            "sewer line blocked and backup times": "sewer_backup",
            "manhole overflow times": "manhole_overflow",
            "catch basin blocked and overflow times": "catch_basin",
        }
    )
    return frame.loc[frame["year"].between(2019, 2022), [
        "year", "ward_id", "sewer_backup", "manhole_overflow", "catch_basin"
    ]]


def _header_cell(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).split("\n")[0].strip()


def _load_floods() -> pd.DataFrame:
    raw = pd.read_excel(FLOODS, sheet_name="Basement Flooding by Ward", header=None)
    header = [_header_cell(c) for c in raw.iloc[1].tolist()]
    body = raw.iloc[2:].copy()
    body.columns = header
    body = body[pd.to_numeric(body["Ward * See Note 1"], errors="coerce").notna()]
    body["ward_id"] = body["Ward * See Note 1"].astype(int)
    body = body[body["ward_id"].between(1, 25)]
    years = ["2019", "2020", "2021", "2022"]
    for year in years:
        body[year] = pd.to_numeric(body[year], errors="coerce")
    body["flood_reports_2019_2022"] = body[years].sum(axis=1)
    body["flood_per_year"] = body[years].mean(axis=1)
    apps = pd.read_excel(FLOODS, sheet_name="BFPSP by Ward", header=None)
    app_header = [_header_cell(c) for c in apps.iloc[1].tolist()]
    apps_body = apps.iloc[2:].copy()
    apps_body.columns = app_header
    apps_body = apps_body[pd.to_numeric(apps_body["Ward * See Note 1"], errors="coerce").notna()]
    apps_body["ward_id"] = apps_body["Ward * See Note 1"].astype(int)
    apps_body = apps_body[apps_body["ward_id"].between(1, 25)]
    for year in years:
        apps_body[year] = pd.to_numeric(apps_body[year], errors="coerce")
    apps_body["subsidy_approvals_2019_2022"] = apps_body[years].sum(axis=1)
    return body[["ward_id", "flood_reports_2019_2022", "flood_per_year"]].merge(
        apps_body[["ward_id", "subsidy_approvals_2019_2022"]], on="ward_id"
    )


def _load_sewer(year: int) -> pd.DataFrame:
    sewer = pd.read_csv(SEWER)
    keep = [
        "ward_id",
        "ward_name",
        "avg_pipe_age",
        "pct_old_pipe",
        "pct_combined_sewer",
        "fd_density",
        "new_pipe_km",
        "pipe_density",
    ]
    snap = sewer.loc[sewer["year"] == year, keep].copy()
    return snap


def _load_trees() -> pd.DataFrame:
    trees = pd.read_excel(TREES)
    trees = trees.rename(columns={"ward_25": "ward_id"})
    trees["ward_id"] = trees["ward_id"].astype(int)
    return trees[
        [
            "ward_id",
            "trees_per_km2",
            "pipe_share_tree_within_5m",
            "pipe_share_in_root_zone",
            "area_km2",
        ]
    ]


def _load_water() -> pd.DataFrame:
    frames = []
    for year in (2019, 2020, 2021, 2022):
        path = WATER_DIR / f"Water_Consumption_{year}.xlsx"
        frame = pd.read_excel(path)
        frame.columns = [str(c).strip().lower() for c in frame.columns]
        frame["ward_id"] = pd.to_numeric(frame["city ward"], errors="coerce")
        frame["year"] = year
        frame["avg_residential_usage"] = pd.to_numeric(
            frame["average residential usage"], errors="coerce"
        )
        frames.append(frame[["ward_id", "year", "avg_residential_usage"]])
    water = pd.concat(frames, ignore_index=True)
    return water[water["ward_id"].between(1, 25)]


def _yearly_wide(frame: pd.DataFrame, value: str, years: tuple[int, ...]) -> pd.DataFrame:
    """One column per year. The score still uses the mean of these values."""
    subset = frame.loc[frame["year"].isin(years), ["ward_id", "year", value]]
    wide = subset.pivot(index="ward_id", columns="year", values=value)
    missing = [year for year in years if year not in wide.columns]
    if missing:
        raise RuntimeError(f"{value} is missing years {missing}")
    wide = wide.loc[:, list(years)]
    wide.columns = [f"{value}_{year}" for year in years]
    return wide.reset_index()


def _year_bits(row, column: str, years: tuple[int, ...], digits: int) -> str:
    return ", ".join(
        f"{year} {float(getattr(row, f'{column}_{year}')):.{digits}f}"
        for year in years
    )


def _mean_z(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    zs = [_z(frame[col]) for col in columns]
    return sum(zs) / len(zs)


def build_scores() -> pd.DataFrame:
    names = _load_sewer(2021)[["ward_id", "ward_name"]]
    sewer_2021 = _load_sewer(2021)
    sewer_2023 = _load_sewer(2023).drop(columns=["ward_name"])
    calls = _load_311()
    complaints = (
        calls.loc[calls["year"].isin(CALL_SCORE_YEARS)]
        .groupby("ward_id", as_index=False)[["sewer_backup", "manhole_overflow", "catch_basin"]]
        .mean()
    )
    call_years = complaints[["ward_id"]]
    for column in CALL_SERIES_COLS:
        call_years = call_years.merge(_yearly_wide(calls, column, CALL_SERIES_YEARS), on="ward_id")
    floods = _load_floods()
    trees = _load_trees()
    water_long = _load_water()
    water = (
        water_long.groupby("ward_id", as_index=False)["avg_residential_usage"]
        .mean()
    )
    water_years = _yearly_wide(water_long, "avg_residential_usage", WATER_YEARS)
    stock = load_subsidy_stock()

    base = (
        names.merge(sewer_2021.drop(columns=["ward_name"]), on="ward_id")
        .merge(complaints, on="ward_id")
        .merge(call_years, on="ward_id")
        .merge(floods, on="ward_id")
        .merge(trees, on="ward_id")
        .merge(water, on="ward_id")
        .merge(water_years, on="ward_id")
        .merge(stock, on="ward_id", how="left")
    )
    base["eligible_homes"] = base["properties_with_fpd"] + base["properties_without_fpd"]
    base["backup_per_1000"] = base["sewer_backup"] / base["eligible_homes"] * 1000
    base["manhole_per_1000"] = base["manhole_overflow"] / base["eligible_homes"] * 1000
    for year in CALL_SERIES_YEARS:
        base[f"backup_per_1000_{year}"] = base[f"sewer_backup_{year}"] / base["eligible_homes"] * 1000
        base[f"manhole_per_1000_{year}"] = base[f"manhole_overflow_{year}"] / base["eligible_homes"] * 1000
    base["flood_per_1000"] = base["flood_per_year"] / base["eligible_homes"] * 1000
    base["subsidy_participation"] = base["properties_with_fpd"] / base["eligible_homes"]

    base["structural_risk"] = _mean_z(base, STRUCTURAL_COLS)
    base["complaint_risk"] = _mean_z(base, COMPLAINT_COLS)
    base["sewage_failure_risk"] = 0.55 * base["structural_risk"] + 0.45 * base["complaint_risk"]
    base["flood_reporting"] = _z(base["flood_per_1000"])
    # High failure pressure and low formal flood reporting.
    base["underreport_gap"] = base["sewage_failure_risk"] - base["flood_reporting"]
    base["participation_z"] = _z(base["subsidy_participation"])
    # High gap and low share of homes that already have a subsidized device.
    base["low_intake_priority"] = base["underreport_gap"] - base["participation_z"]

    # 2025: infrastructure as of 2023, aged two more years, plus a credit for
    # pipes actually installed during 2019-2023.
    installed = (
        pd.read_csv(SEWER)
        .groupby("ward_id", as_index=False)["new_pipe_km"]
        .mean()
        .rename(columns={"new_pipe_km": "mean_new_pipe_km"})
    )
    proj = base[
        [
            "ward_id",
            "eligible_homes",
            "backup_per_1000",
            "manhole_per_1000",
            "flood_per_1000",
            "pipe_share_in_root_zone",
            "avg_residential_usage",
            "subsidy_participation",
        ]
    ].merge(sewer_2023, on="ward_id").merge(installed, on="ward_id")
    proj["avg_pipe_age"] = proj["avg_pipe_age"] + 2
    proj["structural_risk_2025"] = _mean_z(proj, STRUCTURAL_COLS)
    proj["complaint_risk_2025"] = _mean_z(proj, COMPLAINT_COLS)
    proj["replacement_credit"] = _z(proj["mean_new_pipe_km"])
    proj["sewage_failure_risk_2025"] = (
        0.55 * proj["structural_risk_2025"]
        + 0.45 * proj["complaint_risk_2025"]
        - 0.15 * proj["replacement_credit"]
    )
    proj["underreport_gap_2025"] = proj["sewage_failure_risk_2025"] - _z(proj["flood_per_1000"])
    proj["low_intake_priority_2025"] = proj["underreport_gap_2025"] - _z(proj["subsidy_participation"])

    out = base.merge(
        proj[
            [
                "ward_id",
                "sewage_failure_risk_2025",
                "underreport_gap_2025",
                "low_intake_priority_2025",
                "mean_new_pipe_km",
            ]
        ],
        on="ward_id",
    )
    # Rank 1 on each axis is the extreme the question asks for. Adding the two
    # ranks keeps a ward off the top 10 unless it is high on failure pressure
    # and low on flood reporting at the same time. A pure difference of
    # z-scores would promote a low-risk ward whose reporting is even lower.
    out["failure_rank"] = out["sewage_failure_risk"].rank(ascending=False, method="min").astype(int)
    out["low_report_rank"] = out["flood_reporting"].rank(ascending=True, method="min").astype(int)
    out["combined_rank_score"] = out["failure_rank"] + out["low_report_rank"]
    out["gap_rank"] = out["combined_rank_score"].rank(ascending=True, method="min").astype(int)

    out["failure_rank_2025"] = out["sewage_failure_risk_2025"].rank(ascending=False, method="min").astype(int)
    out["combined_rank_score_2025"] = out["failure_rank_2025"] + out["low_report_rank"]
    out["gap_rank_2025"] = out["combined_rank_score_2025"].rank(ascending=True, method="min").astype(int)

    out["low_participation_rank"] = out["subsidy_participation"].rank(ascending=True, method="min").astype(int)
    out["low_intake_score"] = out["combined_rank_score"] + out["low_participation_rank"]
    out["low_intake_rank"] = out["low_intake_score"].rank(ascending=True, method="min").astype(int)
    return out.sort_values(["gap_rank", "ward_id"]).reset_index(drop=True)


def _ward_text(row) -> str:
    """One searchable passage. Strong ranks are named so a question can find them."""
    failure = int(row.failure_rank)
    report = int(row.low_report_rank)
    gap = int(row.gap_rank)
    intake = int(row.low_intake_rank)
    pct = float(row.subsidy_participation) * 100
    reports = int(row.flood_reports_2019_2022)
    parts = [f"Ward {int(row.ward_id)} {row.ward_name}, from the ward index."]
    if failure <= 5:
        parts.append(
            f"Sewer backups are high. Sewage-failure pressure is among the highest in the city, rank {failure} of 25. "
            "That pressure comes from older or combined pipe, tree roots over the sewer, "
            "residential water use, and sewer-backup and manhole-overflow calls."
        )
    elif failure <= 10:
        parts.append(
            f"Sewer backups are relatively high. Sewage-failure rank {failure} of 25."
        )
    elif failure >= 20:
        parts.append(
            f"Sewage-failure pressure is among the lowest in the city, rank {failure} of 25."
        )
    else:
        parts.append(f"Sewage-failure pressure is near the middle of the city, rank {failure} of 25.")
    details = []
    if float(row.pct_old_pipe) >= 0.4:
        details.append("a large share of the pipe is old")
    if float(row.pct_combined_sewer) >= 0.25:
        details.append("a large share of the sewer is combined")
    if float(row.pipe_share_in_root_zone) >= 0.1:
        details.append("tree roots cover a noticeable share of the pipe")
    if float(row.fd_density) > 0:
        details.append("foundation drains are connected")
    if details:
        parts.append("In this ward, " + ", ".join(details) + ".")
    parts.append(
        f"There were about {float(row.backup_per_1000):.1f} sewer-backup calls "
        "per 1,000 eligible homes in 2019-2021, the mean of "
        f"{_year_bits(row, 'backup_per_1000', CALL_SCORE_YEARS, 1)}. "
        f"2022 is a partial extract, {float(row.backup_per_1000_2022):.1f} per 1,000, and is not in that mean."
    )
    parts.append(
        "Manhole-overflow calls per 1,000 eligible homes by year, same window: "
        f"{_year_bits(row, 'manhole_per_1000', CALL_SCORE_YEARS, 2)}. "
        f"The 2022 partial extract is {float(row.manhole_per_1000_2022):.2f} per 1,000."
    )
    parts.append(
        "Average residential water use by year: "
        f"{_year_bits(row, 'avg_residential_usage', WATER_YEARS, 1)}. "
        "The score uses the mean of those four years."
    )
    if report <= 5:
        parts.append(
            "Residents rarely report basement floods compared with other wards. "
            f"Flood-report rank {report} of 25, where 1 means the fewest basement-flood "
            f"requests per eligible home. The ward recorded {reports} basement-flood requests from 2019 to 2022."
        )
    elif report >= 20:
        parts.append(
            "Residents report basement floods more often than most wards. "
            f"Flood-report rank {report} of 25. The ward recorded {reports} basement-flood requests from 2019 to 2022."
        )
    else:
        parts.append(
            f"Basement-flood reporting is mid-range, flood-report rank {report} of 25. "
            f"The ward recorded {reports} basement-flood requests from 2019 to 2022."
        )
    without = int(row.properties_without_fpd)
    with_device = int(row.properties_with_fpd)
    if pct < 5:
        parts.append(
            f"Very few eligible homes already have a subsidized flood device, {pct:.1f} percent. "
            f"{without} homes are still without a device and {with_device} already have one. "
            "Subsidy uptake is among the lowest."
        )
    elif pct < 12:
        parts.append(
            f"Subsidy uptake is low: {pct:.1f} percent of eligible homes already have a subsidized flood device. "
            f"{without} homes are still without one."
        )
    else:
        parts.append(
            f"{pct:.1f} percent of eligible homes already have a subsidized flood device. "
            f"{without} homes are still without one and {with_device} already have one."
        )
    if intake <= 5:
        parts.append(
            f"This ward is a strong outreach candidate. Outreach rank {intake} of 25, "
            "combining sewage-failure pressure, rare flood reporting, and low device uptake."
        )
    elif intake <= 10:
        parts.append(
            f"Outreach rank {intake} of 25. It is a plausible place for more subsidy outreach."
        )
    else:
        parts.append(
            f"Outreach rank {intake} of 25, so it is not at the front of the citywide outreach list."
        )
    if gap <= 5:
        parts.append(
            f"The gap between sewage-failure pressure and basement-flood reporting is among the widest, "
            f"gap rank {gap} of 25."
        )
    parts.append(
        f"On the 2025 pipe update, sewage-failure rank is {int(row.failure_rank_2025)} of 25 "
        f"and gap rank is {int(row.gap_rank_2025)} of 25. That update ages the pipes; it is not a storm forecast."
    )
    return " ".join(parts)


def _ranking_passage(scores: pd.DataFrame, column: str, title: str, gloss: str, limit: int = 8) -> dict:
    ordered = scores.sort_values([column, "ward_id"]).head(limit)
    lines = [title, gloss]
    for _, row in ordered.iterrows():
        lines.append(f"{int(row[column])}. Ward {int(row.ward_id)} {row.ward_name}.")
    return {"ward_id": None, "page": 0, "text": "\n".join(lines)}


def ward_passages(scores: pd.DataFrame) -> list[dict]:
    """Plain-language ward index documents for the same search as the PDFs."""
    passages = [
        {"ward_id": int(row.ward_id), "page": int(row.ward_id), "text": _ward_text(row)}
        for _, row in scores.sort_values("ward_id").iterrows()
    ]
    passages.append(
        _ranking_passage(
            scores,
            "low_intake_rank",
            "Ward index outreach ranking.",
            "Use this list to decide which wards to outreach when sewer backups are high, "
            "few residents report basement floods, and few homes already have a subsidized flood device. "
            "Rank 1 is the first ward to contact.",
        )
    )
    passages.append(
        _ranking_passage(
            scores,
            "failure_rank",
            "Ward index sewage-failure ranking.",
            "Rank 1 has the highest sewage-failure pressure from older or combined pipe, "
            "tree roots over the sewer, residential water use, and sewer-backup calls.",
        )
    )
    passages.append(
        _ranking_passage(
            scores,
            "low_report_rank",
            "Ward index basement-flood reporting ranking.",
            "Rank 1 has the fewest basement-flood reports per eligible home, 2019 to 2022.",
        )
    )
    passages.append(
        _ranking_passage(
            scores,
            "gap_rank",
            "Ward index gap ranking.",
            "Rank 1 has the widest gap between high sewage-failure pressure and few basement-flood reports.",
        )
    )
    return passages


_FAILURE = re.compile(
    r"pipe|sewer|sewage|backup|combined|root|manhole|failure", re.I
)
_REPORTING = re.compile(
    r"under-?\s*report|\breport|flood report|\bgap\b",
    re.I,
)
_OUTREACH = re.compile(
    r"outreach|subsid|intake|device|unprotected|participation|contact",
    re.I,
)


def _focus(question: str) -> tuple[str, bool]:
    """Return which rank answers the question, and whether to use the 2025 update."""
    failure = bool(_FAILURE.search(question))
    reporting = bool(_REPORTING.search(question))
    outreach = bool(_OUTREACH.search(question))
    use_2025 = "2025" in question
    if failure and not reporting and not outreach:
        return "failure", use_2025
    if reporting and not outreach:
        return "gap", use_2025
    return "outreach", use_2025


def _mentioned_ward_ids(scores: pd.DataFrame, question: str) -> set[int]:
    ids: set[int] = set()
    for raw in re.findall(r"ward\s*(\d{1,2})", question, flags=re.I):
        number = int(raw)
        if 1 <= number <= 25:
            ids.add(number)
    folded = question.lower()
    for _, row in scores.iterrows():
        name = str(row.ward_name).lower()
        if name and name in folded:
            ids.add(int(row.ward_id))
            continue
        for part in re.split(r"[\s\-]+", name):
            if len(part) >= 6 and re.search(rf"\b{re.escape(part)}\b", folded):
                ids.add(int(row.ward_id))
                break
    return ids


def select_wards(scores: pd.DataFrame, question: str, n: int = 5) -> tuple[pd.DataFrame, str]:
    """Pick ward rows for the web API. The ask command retrieves passages instead."""
    focus, use_2025 = _focus(question)
    frame = scores.copy()
    if focus == "failure":
        rank_col = "failure_rank_2025" if use_2025 else "failure_rank"
        basis = (
            "sewage-failure pressure: older or combined pipe, tree roots over pipe, "
            "residential water use, and sewer-backup and manhole-overflow calls "
            "per 1,000 eligible homes"
        )
    elif focus == "gap":
        rank_col = "gap_rank_2025" if use_2025 else "gap_rank"
        basis = (
            "high sewage-failure pressure together with few basement-flood reports "
            "per eligible home"
        )
    elif use_2025:
        frame["priority_rank"] = (
            frame["low_intake_priority_2025"].rank(ascending=False, method="min").astype(int)
        )
        rank_col = "priority_rank"
        basis = (
            "outreach priority on the 2025 scores, combining sewage-failure pressure, "
            "how rarely residents report basement floods, and how few eligible homes "
            "already have a subsidized device"
        )
    else:
        rank_col = "low_intake_rank"
        basis = (
            "outreach priority, the sum of three ranks: sewage-failure pressure, "
            "how rarely residents report basement floods, and how few eligible homes "
            "already have a subsidized device"
        )
    if rank_col != "priority_rank":
        frame["priority_rank"] = frame[rank_col].astype(int)
    if use_2025:
        basis += (
            ". The sewage-failure side uses the 2025 structural update "
            "(2023 pipes aged two years, with a credit for new pipe, complaint rates held fixed). "
            "It is not a forecast of storms"
        )
    frame["shown_failure_rank"] = frame[
        "failure_rank_2025" if use_2025 else "failure_rank"
    ].astype(int)
    ranked = frame.sort_values(["priority_rank", "ward_id"])
    named = _mentioned_ward_ids(frame, question)
    if not named:
        chosen = ranked.head(n)
        scope = f"the {len(chosen)} highest-priority wards in the city"
    else:
        matched = ranked[ranked["ward_id"].isin(named)]
        if len(matched) == 1:
            rest = ranked[~ranked["ward_id"].isin(named)].head(n)
            chosen = pd.concat([matched, rest], ignore_index=True)
            scope = "the ward named in the question, then the highest-priority wards for comparison"
        else:
            chosen = matched.head(8)
            scope = "the wards named in the question, highest priority first"
    return chosen.reset_index(drop=True), f"{basis}. Showing {scope}"


def format_ward_brief(selected: pd.DataFrame, basis: str) -> str:
    """Lay-language lines used by the web API."""
    lines = [
        f"Ward index used for this answer: {basis}.",
        "Priority rank 1 is the strongest match. "
        "Eligible homes are single-family, duplex, and triplex properties in the subsidy program. "
        "Device share is the June 2025 stock. "
        "Flood reports are 2019-2022. Sewer-backup rates are 2019-2021.",
    ]
    for _, row in selected.iterrows():
        lines.append(
            f"Ward {int(row.ward_id)} ({row.ward_name}): "
            f"priority rank {int(row.priority_rank)} of 25; "
            f"sewage-failure rank {int(row.shown_failure_rank)} of 25 "
            f"(1 means the highest sewage-failure pressure, 25 the lowest); "
            f"flood-report rank {int(row.low_report_rank)} of 25 "
            f"(1 means the fewest basement-flood requests per eligible home); "
            f"{row.subsidy_participation * 100:.1f}% of eligible homes already have a subsidized flood device; "
            f"{int(row.properties_without_fpd)} homes are still without one."
        )
    return "\n".join(lines)


def top_table(scores: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = [
        "gap_rank",
        "ward_id",
        "ward_name",
        "failure_rank",
        "low_report_rank",
        "sewage_failure_risk",
        "flood_reporting",
        "gap_rank_2025",
        "subsidy_participation",
        "properties_with_fpd",
        "properties_without_fpd",
        "subsidy_approvals_2019_2022",
        "flood_reports_2019_2022",
    ]
    return scores.nsmallest(n, "gap_rank")[cols].copy()
