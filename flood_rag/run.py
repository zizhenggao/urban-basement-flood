"""Build the ward index and answer a planner question from both sources.

    python -m flood_rag.run
    python -m flood_rag.run ask "Which wards should we outreach because backups are high, few residents report floods, and few homes have a device?"
"""

from __future__ import annotations

import argparse
import textwrap

from flood_rag import service
from flood_rag.paths import OUTPUT
from flood_rag.policy import PolicyIndex, load_chunks, load_passages, save_chunks
from flood_rag.score import build_scores


def _pct(frame):
    out = frame.copy()
    out["subsidy_participation"] = (out["subsidy_participation"] * 100).round(1)
    if "sewage_failure_risk" in out.columns:
        out["sewage_failure_risk"] = out["sewage_failure_risk"].round(2)
    if "flood_reporting" in out.columns:
        out["flood_reporting"] = out["flood_reporting"].round(2)
    return out


def _print_top(scores) -> None:
    cols = [
        "ward_id", "ward_name", "failure_rank", "low_report_rank", "gap_rank_2025",
        "subsidy_participation", "flood_reports_2019_2022", "properties_with_fpd",
        "properties_without_fpd",
    ]
    print("\nHighest sewage-failure pressure (rank 1 = highest)\n")
    print(_pct(scores.nsmallest(10, "failure_rank")[cols]).to_string(index=False))
    print("\nLowest basement-flood reporting, 2019-2022 (rank 1 = fewest reports per eligible home)\n")
    print(_pct(scores.nsmallest(10, "low_report_rank")[cols]).to_string(index=False))
    both = scores[(scores["failure_rank"] <= 10) & (scores["low_report_rank"] <= 10)]
    print("\nIn both top 10s at once (high failure pressure and low flood reporting)\n")
    if both.empty:
        print("None. No ward is in the top 10 on both lists.")
    else:
        print(_pct(both.sort_values("failure_rank")[cols]).to_string(index=False))
    high_risk = scores[scores["failure_rank"] <= 10].nsmallest(10, "subsidy_participation")
    print("\nSubsidy participation inside the 10 highest-failure wards (June 2025 device stock)\n")
    print(_pct(high_risk[cols]).to_string(index=False))
    print("\nLowest subsidy participation in the city, with failure rank beside it\n")
    print(_pct(scores.nsmallest(10, "subsidy_participation")[cols]).to_string(index=False))
    moved = scores.assign(shift=scores["gap_rank_2025"] - scores["gap_rank"])
    moved = moved.reindex(moved["shift"].abs().sort_values(ascending=False).index).head(5)
    print("\nLargest 2025 rank moves (negative means the ward rose in the gap ranking)\n")
    print(
        moved[["ward_id", "ward_name", "gap_rank", "gap_rank_2025", "shift", "mean_new_pipe_km"]]
        .to_string(index=False)
    )


def _print_hits(title: str, hits) -> None:
    print(f"\n{title}\n")
    if not hits:
        print("None.\n")
        return
    for hit in hits:
        ward = f" ward {hit.ward_id}" if hit.ward_id else ""
        print(f"--- {hit.source} p.{hit.page}{ward}  score {hit.score:.3f}")
        print(textwrap.shorten(hit.text.replace("\n", " "), width=500))
        print()


def _ask(scores, question: str, model: str, k: int) -> None:
    chunks = load_chunks()
    save_chunks(chunks)
    index = PolicyIndex(load_passages(chunks), sublinear_tf=True)
    result = service.answer(scores, index, question, k=k, model=model)

    if result.kind == "unknown":
        print(f"\n{result.help}\n")
        return
    if result.wards:
        print(f"\n{result.brief}\n")
    if result.kind in ("program", "both"):
        _print_hits(f"Program document passages for: {question}", result.passages)

    if not model:
        print("Pass --model to have a local model turn the above into a paragraph.")
        return
    if result.llm_answer:
        print(result.llm_answer)
    else:
        print(
            "Ollama did not answer. Start it with `ollama serve` and pull a small model, "
            f"for example `ollama pull {model}`."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Local basement-flood ward index")
    sub = parser.add_subparsers(dest="cmd")
    ask = sub.add_parser("ask", help="Rank wards from the index, then retrieve policy pages")
    ask.add_argument("question")
    ask.add_argument("--model", default="", help="Ollama model name, e.g. qwen2.5:1.5b")
    ask.add_argument("-k", type=int, default=4)
    args = parser.parse_args()

    scores = build_scores()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "ward_index.csv"
    # Rounded so the CSV is byte-identical across runs and library versions.
    scores.round(6).to_csv(out_path, index=False)

    if args.cmd == "ask":
        _ask(scores, args.question, args.model, args.k)
        return

    _print_top(scores)
    print(f"\nWrote {out_path}")
    print(
        "\nCaveats: 311 rates use 2019-2021 because the local 2022 file is partial. "
        "Flood reports use 2019-2022. The 2025 column ages the 2023 sewer snapshot "
        "and holds complaint rates fixed; it is not a forecast of 2025 storms. "
        "Subsidy participation is the June 2025 device stock on the ward-profile PDF."
    )


if __name__ == "__main__":
    main()
