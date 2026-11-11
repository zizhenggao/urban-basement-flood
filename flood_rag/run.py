"""Build the ward index and answer a planner question from both sources.

    python -m flood_rag.run
    python -m flood_rag.run ask "Which wards should we outreach because backups are high, few residents report floods, and few homes have a device?"
"""

from __future__ import annotations

import argparse
import textwrap

from flood_rag.paths import OUTPUT
from flood_rag.policy import Chunk, PolicyIndex, load_chunks, ollama_answer, save_chunks
from flood_rag.score import build_scores, ward_passages


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
    for chunk, score in hits:
        if chunk.source == "ward index":
            where = "ranking" if chunk.ward_id is None else f"ward {chunk.ward_id}"
            label = f"ward index {where}"
        else:
            ward = f" ward {chunk.ward_id}" if chunk.ward_id else ""
            label = f"{chunk.source} p.{chunk.page}{ward}"
        print(f"--- {label}  score {score:.3f}")
        print(textwrap.shorten(chunk.text.replace("\n", " "), width=500))
        print()


def prepare_index(scores):
    """Policy pages and ward-index passages in one TF-IDF index."""
    chunks = load_chunks()
    for passage in ward_passages(scores):
        chunks.append(Chunk("ward index", passage["page"], passage["ward_id"], passage["text"]))
    save_chunks(chunks)
    return PolicyIndex(chunks)


def answer_question(index, question: str, model: str, k: int):
    """Retrieve from both sources and generate an answer from those excerpts."""
    hits = index.search(question, k=k)
    answer, error = ollama_answer(question, hits, model)
    return hits, answer, error


def _ask(scores, question: str, model: str, k: int) -> None:
    index = prepare_index(scores)
    hits = index.search(question, k=k)
    _print_hits(f"Retrieved from the ward index and the policy PDFs: {question}", hits)
    print(f"Generating an answer with {model} from those excerpts.\n")
    answer, error = ollama_answer(question, hits, model)
    if error:
        print(error)
        return
    print(answer)
    path = OUTPUT / "ask_answer.txt"
    path.write_text(f"Question: {question}\n\n{answer}\n", encoding="utf-8")
    print(f"\nWrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local basement-flood ward index")
    sub = parser.add_subparsers(dest="cmd")
    ask = sub.add_parser("ask", help="Retrieve both sources, then generate an answer")
    ask.add_argument("question")
    ask.add_argument("--model", default="qwen2.5:1.5b", help="Local Ollama model used to write the answer")
    ask.add_argument("-k", type=int, default=4)
    evaluate = sub.add_parser("eval", help="Score ask with RAGAS on a fixed local question set")
    evaluate.add_argument("--model", default="qwen2.5:1.5b", help="Ollama model that writes the answers")
    evaluate.add_argument("--judge", default="", help="Ollama model that scores the answers. Defaults to --model.")
    evaluate.add_argument("-k", type=int, default=4)
    args = parser.parse_args()

    scores = build_scores()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "ward_index.csv"
    # Rounded so the CSV is byte-identical across runs and library versions.
    scores.round(6).to_csv(out_path, index=False)

    if args.cmd == "ask":
        _ask(scores, args.question, args.model, args.k)
        return

    if args.cmd == "eval":
        from flood_rag.evaluate import evaluate_rag

        judge = args.judge or args.model
        evaluate_rag(scores, args.model, judge, args.k)
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
