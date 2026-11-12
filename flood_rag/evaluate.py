"""Score the ask path with RAGAS. The judge is a local Ollama model.

    python -m flood_rag.run eval
"""

from __future__ import annotations

import os

import pandas as pd

from flood_rag.paths import OUTPUT
from flood_rag.run import answer_question, prepare_index


def _allow_ragas_import() -> None:
    """RAGAS 0.4 imports a Vertex class that current LangChain no longer ships.

    The eval uses Ollama, so the missing class is only needed for that import.
    """
    import sys
    import types

    name = "langchain_community.chat_models.vertexai"
    if name in sys.modules:
        return
    try:
        __import__(name)
    except ModuleNotFoundError:
        stub = types.ModuleType(name)

        class ChatVertexAI:
            pass

        stub.ChatVertexAI = ChatVertexAI
        sys.modules[name] = stub


def _top(scores: pd.DataFrame, column: str, n: int = 5) -> str:
    ordered = scores.sort_values([column, "ward_id"]).head(n)
    return "; ".join(
        f"Ward {int(row.ward_id)} {row.ward_name} at rank {int(row[column])}"
        for _, row in ordered.iterrows()
    )


def eval_cases(scores: pd.DataFrame) -> list[dict]:
    """Questions whose reference answers are read off the ward index ranks."""
    return [
        {
            "user_input": (
                "Which wards should we outreach first because sewer backups are high, "
                "few residents report basement floods, and few homes already have a subsidized device?"
            ),
            "reference": (
                "Contact these wards first for basement-flood outreach: "
                f"{_top(scores, 'low_intake_rank')}. "
                "Rank 1 is the first ward to contact. The rank combines sewage-failure pressure, "
                "rare basement-flood reporting, and low uptake of the subsidized flood device."
            ),
        },
        {
            "user_input": (
                "Which wards have the highest sewage-failure pressure from older or combined pipe, "
                "tree roots over the sewer, and sewer-backup calls?"
            ),
            "reference": (
                "The highest sewage-failure pressure is "
                f"{_top(scores, 'failure_rank')}. Rank 1 is the highest pressure."
            ),
        },
        {
            "user_input": (
                "Which wards have the widest gap between high sewage-failure pressure "
                "and few basement-flood reports?"
            ),
            "reference": (
                "The widest gap is "
                f"{_top(scores, 'gap_rank')}. Rank 1 is the widest gap."
            ),
        },
    ]


def contexts_for_judge(texts: list[str], limit: int = 700) -> list[str]:
    """Keep readable sentences. Diagram pages make the 1.5B judge skip the JSON verdict."""
    kept = []
    for text in texts:
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if len(stripped) < 40:
                continue
            letters = sum(character.isalpha() for character in stripped)
            if letters / len(stripped) < 0.55:
                continue
            lines.append(stripped)
        cleaned = " ".join(lines)
        if not cleaned:
            letters = sum(character.isalpha() for character in text)
            if text and letters / len(text) >= 0.6:
                cleaned = " ".join(text.split())
        cleaned = cleaned[:limit].strip()
        if cleaned:
            kept.append(cleaned)
    return kept


def _samples(scores: pd.DataFrame, model: str, k: int) -> list[dict]:
    index = prepare_index(scores)
    rows = []
    for case in eval_cases(scores):
        question = case["user_input"]
        print(f"\nAnswering: {question}\n")
        hits, answer, error = answer_question(index, question, model, k)
        if error:
            raise RuntimeError(error)
        print(answer)
        rows.append(
            {
                "user_input": question,
                "retrieved_contexts": contexts_for_judge([hit.text for hit, _ in hits]),
                "response": answer,
                "reference": case["reference"],
            }
        )
    return rows


def judge_llm(judge: str):
    """Local judge that must return JSON, with room for the classification list."""
    _allow_ragas_import()
    from langchain_ollama import ChatOllama
    from ragas.llms import LangchainLLMWrapper

    return LangchainLLMWrapper(
        ChatOllama(model=judge, temperature=0, format="json", num_predict=2048)
    )


def evaluate_rag(scores: pd.DataFrame, model: str, judge: str, k: int) -> None:
    """Run the three questions, then score retrieval and the generated answers."""
    os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
    _allow_ragas_import()
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import Faithfulness, FactualCorrectness, LLMContextRecall
    from ragas.run_config import RunConfig

    rows = _samples(scores, model, k)
    evaluator = judge_llm(judge)
    print(f"\nScoring {len(rows)} answers with RAGAS. The judge is {judge}.\n")
    result = evaluate(
        dataset=EvaluationDataset.from_list(rows),
        metrics=[LLMContextRecall(), Faithfulness(), FactualCorrectness()],
        llm=evaluator,
        run_config=RunConfig(timeout=600, max_retries=1, max_workers=1),
        raise_exceptions=False,
        show_progress=True,
    )
    frame = result.to_pandas()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "ragas_eval.csv"
    frame.to_csv(path, index=False)
    print(result)
    print(f"\nWrote {path}")
    print(
        "\nContext recall asks whether the retrieved ward-index and policy excerpts "
        "cover the reference. Faithfulness asks whether the answer stays inside those "
        "excerpts. Factual correctness compares the answer with the reference ranks. "
        "The judge is the local model, so the scores are a check on this pipeline, "
        "not a published benchmark. A blank score means that model did not return "
        "a verdict RAGAS could read for that metric."
    )
