"""Answer a planner question and return structured data.

Shared by the command line (flood_rag.run) and the web API so both give the
same result. Nothing here prints or writes files.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from flood_rag import router
from flood_rag.policy import Chunk, PolicyIndex, ollama_answer
from flood_rag.score import _mentioned_ward_ids, format_ward_brief, select_wards


@dataclass
class Excerpt:
    source: str
    page: int
    ward_id: int | None
    score: float
    text: str


@dataclass
class Answer:
    question: str
    kind: str  # 'program', 'wards', 'both' or 'unknown'
    basis: str = ""
    brief: str = ""
    wards: list[dict] = field(default_factory=list)
    passages: list[Excerpt] = field(default_factory=list)
    topic: str | None = None
    topic_label: str | None = None
    help: str | None = None  # set when the question was not understood
    model: str = ""
    llm_answer: str | None = None
    llm_available: bool | None = None  # None when no model was requested


def _excerpt(hit: tuple[Chunk, float]) -> Excerpt:
    chunk, score = hit
    return Excerpt(chunk.source, chunk.page, chunk.ward_id, float(score), chunk.text)


def _ward_rows(selected: pd.DataFrame) -> list[dict]:
    rows = []
    for _, row in selected.iterrows():
        rows.append(
            {
                "ward_id": int(row.ward_id),
                "ward_name": str(row.ward_name),
                "priority_rank": int(row.priority_rank),
                "failure_rank": int(row.shown_failure_rank),
                "low_report_rank": int(row.low_report_rank),
                "subsidy_participation": float(row.subsidy_participation),
                "properties_with_fpd": int(row.properties_with_fpd),
                "properties_without_fpd": int(row.properties_without_fpd),
                "flood_reports_2019_2022": int(row.flood_reports_2019_2022),
                "topic_rank": int(row.topic_rank) if "topic_rank" in row else None,
                "topic_value": str(row.topic_value) if "topic_value" in row else None,
            }
        )
    return rows


# topic -> (label, column, lowest first?, plain-language value, how the ranking reads)
TOPICS = {
    "old_pipe": (
        "Older sewer pipe", "pct_old_pipe", False,
        lambda v: f"{v * 100:.0f}% of sewer pipe is past the old-pipe age",
        "share of sewer pipe past the old-pipe age, highest first",
    ),
    "combined": (
        "Combined sewers", "pct_combined_sewer", False,
        lambda v: f"{v * 100:.0f}% of pipe carries sewage and stormwater together",
        "share of pipe that is combined sewer, highest first",
    ),
    "backup": (
        "Sewer backups", "backup_per_1000", False,
        lambda v: f"{v:.1f} sewer-backup calls per 1,000 eligible homes (2019-2021 average)",
        "sewer-backup calls per 1,000 eligible homes, highest first",
    ),
    "roots": (
        "Tree roots over pipe", "pipe_share_in_root_zone", False,
        lambda v: f"{v * 100:.0f}% of pipe lies in a tree-root zone",
        "share of pipe inside a tree-root zone, highest first",
    ),
    "reports": (
        "Basement-flood reports", "flood_per_1000", False,
        lambda v: f"{v:.1f} basement-flood requests per year per 1,000 eligible homes (2019-2022)",
        "basement-flood requests per eligible home, highest first",
    ),
    "subsidy": (
        "Low subsidy uptake", "subsidy_participation", True,
        lambda v: f"{v * 100:.1f}% of eligible homes have a subsidized device (June 2025)",
        "share of eligible homes with a subsidized device, lowest first",
    ),
}


def rank_by_topic(
    scores: pd.DataFrame, topic: str, named_ids: set[int] | None = None, n: int = 5
) -> tuple[pd.DataFrame, str]:
    """Order the wards by one table column. Named wards stay in the list."""
    label, column, lowest_first, describe, how = TOPICS[topic]
    frame = scores.copy()
    frame["topic_rank"] = frame[column].rank(ascending=lowest_first, method="min").astype(int)
    frame["topic_value"] = frame[column].map(lambda v: describe(float(v)))
    frame["priority_rank"] = frame["low_intake_rank"].astype(int)
    frame["shown_failure_rank"] = frame["failure_rank"].astype(int)
    ranked = frame.sort_values(["topic_rank", "ward_id"])
    if named_ids:
        matched = ranked[ranked["ward_id"].isin(named_ids)]
        if len(matched) == 1:
            rest = ranked[~ranked["ward_id"].isin(named_ids)].head(n)
            chosen = pd.concat([matched, rest], ignore_index=True)
            scope = "the ward named in the question, then the top wards for comparison"
        else:
            chosen = matched.head(8)
            scope = "the wards named in the question"
    else:
        chosen = ranked.head(n)
        scope = f"the top {len(chosen)} wards in the city"
    return chosen.reset_index(drop=True), f"{label}: wards ranked by {how}. Showing {scope}"


def _topic_brief(selected: pd.DataFrame, basis: str) -> str:
    lines = [f"Ward table used for this answer: {basis}.", "Rank 1 is the strongest match on this topic."]
    for _, row in selected.iterrows():
        lines.append(
            f"Ward {int(row.ward_id)} ({row.ward_name}): rank {int(row.topic_rank)} of 25; {row.topic_value}."
        )
    return "\n".join(lines)


HIGH_CUTOFF = 70
MEDIUM_CUTOFF = 40

# column -> (label, how to say the ward's value in plain language)
_FACTORS = {
    "pct_old_pipe": ("Older pipe", lambda v: f"{v * 100:.0f}% of sewer pipe is past the old-pipe age"),
    "pct_combined_sewer": ("Combined sewers", lambda v: f"{v * 100:.0f}% of pipe carries sewage and stormwater together"),
    "avg_pipe_age": ("Pipe age", lambda v: f"average pipe age is {v:.0f} years"),
    "pipe_share_in_root_zone": ("Tree roots over pipe", lambda v: f"{v * 100:.0f}% of pipe lies in a tree-root zone"),
    "avg_residential_usage": ("Water use", lambda v: f"average residential water use is {v:.0f}"),
    "backup_per_1000": ("Sewer backups", lambda v: f"{v:.1f} sewer-backup calls per 1,000 eligible homes"),
    "manhole_per_1000": ("Manhole overflows", lambda v: f"{v:.1f} manhole-overflow calls per 1,000 eligible homes"),
    # The next two count as a factor when the value is LOW: they are the other
    # two parts of the outreach rank (few flood reports, few homes with a device).
    "flood_per_1000": ("Few flood reports", lambda v: f"{v:.1f} basement-flood requests per year per 1,000 eligible homes"),
    "subsidy_participation": ("Few homes with a device", lambda v: f"only {v * 100:.1f}% of eligible homes have a subsidized device"),
}
_LOW_IS_A_FACTOR = {"flood_per_1000", "subsidy_participation"}
# fd_density is left out: it is 0 for 22 of 25 wards, so any small value looks extreme.
FACTOR_MIN_Z = 0.5  # only show factors clearly above the city average


def priority_score(rank: int, n: int) -> int:
    """Rank 1 -> 100, rank n -> 0, evenly spaced. An order, not a probability."""
    if n <= 1:
        return 100
    return round(100 * (n - rank) / (n - 1))


def priority_level(score: int) -> str:
    if score >= HIGH_CUTOFF:
        return "High"
    if score >= MEDIUM_CUTOFF:
        return "Medium"
    return "Low"


def ward_table(scores: pd.DataFrame) -> list[dict]:
    """All wards with a 0-100 outreach-priority score, its level and top factors."""
    n = len(scores)
    zs = {}
    for col in _FACTORS:
        std = float(scores[col].std(ddof=0))
        z = (scores[col] - scores[col].mean()) / std if std else scores[col] * 0.0
        zs[col] = -z if col in _LOW_IS_A_FACTOR else z
    rows = []
    for idx, row in scores.iterrows():
        rank = int(row.low_intake_rank)
        score = priority_score(rank, n)
        ranked = [
            c
            for c in sorted(_FACTORS, key=lambda c: float(zs[c].loc[idx]), reverse=True)
            if float(zs[c].loc[idx]) >= FACTOR_MIN_Z
        ][:3]
        rows.append(
            {
                "ward_id": int(row.ward_id),
                "ward_name": str(row.ward_name),
                "priority_rank": rank,
                "score": score,
                "level": priority_level(score),
                "top_factors": [
                    {"label": _FACTORS[c][0], "detail": _FACTORS[c][1](float(row[c]))}
                    for c in ranked
                ],
                "failure_rank": int(row.failure_rank),
                "low_report_rank": int(row.low_report_rank),
                "subsidy_participation": float(row.subsidy_participation),
                "eligible_homes": int(row.eligible_homes),
                "properties_without_fpd": int(row.properties_without_fpd),
                "flood_reports_2019_2022": int(row.flood_reports_2019_2022),
            }
        )
    return sorted(rows, key=lambda r: (r["priority_rank"], r["ward_id"]))


def answer(
    scores: pd.DataFrame,
    index: PolicyIndex,
    question: str,
    k: int = 3,
    model: str = "",
) -> Answer:
    """Answer from the ward table, the program PDFs, both, or say what can be asked.

    `index` must be built from passages (flood_rag.policy.load_passages).
    """
    named = _mentioned_ward_ids(scores, question)
    kind = router.classify(question, bool(named))
    result = Answer(question=question, kind=kind, model=model)
    if kind == "unknown":
        result.help = router.HELP
        return result

    hits: list[tuple[Chunk, float]] = []
    if kind in ("wards", "both"):
        topic = router.detect_topic(question)
        if topic:
            selected, basis = rank_by_topic(scores, topic, named)
            result.topic, result.topic_label = topic, TOPICS[topic][0]
            brief = _topic_brief(selected, basis)
        else:
            selected, basis = select_wards(scores, question)
            brief = format_ward_brief(selected, basis)
        result.basis, result.brief, result.wards = basis, brief, _ward_rows(selected)
    if kind in ("program", "both"):
        hits = index.search(question, k=k)
        result.passages = [_excerpt(hit) for hit in hits]

    if model:
        text, _error = ollama_answer(question, hits, model, result.brief)
        result.llm_answer = text
        result.llm_available = text is not None
    return result
