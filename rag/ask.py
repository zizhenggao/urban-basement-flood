"""Ask a question against the ward index and the policy-context PDFs.

Ranks and counts come from outputs/ward_index.csv. Program rules come from
the pages retrieved out of policy context/. The model may only word the
answer from those two blocks.

    .\\.venv-rag\\Scripts\\python -m rag.ask "Which wards should we outreach, and what does the subsidy program offer them?"
    .\\.venv-rag\\Scripts\\python -m rag.ask --retrieve-only "basement flooding subsidy intake in Scarborough"
"""

from __future__ import annotations

import argparse
import re
import sys

import pandas as pd
import requests
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from flood_rag.score import format_ward_brief, select_wards
from rag.config import INDEX_DIR, OLLAMA_BASE_URL, OLLAMA_MODEL, WARD_INDEX
from rag.embeddings import LocalEmbeddings

PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer questions for a City of Toronto basement-flood planning review. "
            "You have two sources. "
            "WARD INDEX is outputs/ward_index.csv. Ranks, rates, eligible homes, pipe shares, "
            "flood counts, and device counts come only from that block. Do not reorder its priority rank. "
            "POLICY EXCERPTS are pages from the policy context folder. Program rules, eligibility, "
            "study areas, and capital projects come only from those excerpts. "
            "policy: one or two sentences on what the program offers those wards, "
            "using only excerpts about those same wards or citywide program rules. "
            "Ignore an excerpt that is about a different ward. "
            "Name the source for each claim: the ward index, or the file and page. "
            "If a source does not contain a fact, say so. "
            "A high score is relative vulnerability for outreach, not a statement that a basement will flood "
            "and not a subsidy decision.",
        ),
        (
            "human",
            "POLICY EXCERPTS\n{context}\n\n"
            "WARD INDEX — these are the only wards you may name, in this order\n{ward_index}\n\n"
            "Question: {question}\n"
 
        ),
    ]
)


def _format_docs(docs) -> str:
    blocks = []
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page")
        kind = doc.metadata.get("source_type", "text")
        where = f"{source} p.{page}" if page else str(source)
        blocks.append(f"[{kind}] {where}\n{doc.page_content}")
    return "\n\n".join(blocks)


def _ollama_is_up() -> bool:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return response.ok
    except requests.RequestException:
        return False


def _round(value, digits: int) -> str:
    try:
        missing = pd.isna(value)
    except TypeError:
        missing = False
    if missing:
        return ""
    if isinstance(value, str):
        return value.strip()
    number = float(value)
    if digits == 0:
        return str(int(round(number)))
    return f"{number:.{digits}f}"


def _ward_index_context(selected: pd.DataFrame, basis: str) -> str:
    view = selected.copy()
    view["subsidy_participation_pct"] = view["subsidy_participation"] * 100
    view["combined_sewer_pct"] = view["pct_combined_sewer"] * 100
    view["old_pipe_pct"] = view["pct_old_pipe"] * 100
    columns = [
        "priority_rank",
        "ward_id",
        "ward_name",
        "shown_failure_rank",
        "low_report_rank",
        "subsidy_participation_pct",
        "properties_with_fpd",
        "properties_without_fpd",
        "eligible_homes",
        "flood_reports_2019_2022",
        "backup_per_1000",
        "combined_sewer_pct",
        "old_pipe_pct",
        "avg_pipe_age",
    ]
    present = [column for column in columns if column in view.columns]
    shown = view[present]
    header = " | ".join(present)
    rows = []
    for row in shown.itertuples(index=False, name=None):
        cells = []
        for column, value in zip(present, row):
            if isinstance(value, str):
                cells.append(value.strip())
                continue
            if column.endswith("_pct") or column == "avg_pipe_age":
                digits = 1
            elif column == "backup_per_1000":
                digits = 2
            else:
                digits = 0
            cells.append(_round(value, digits))
        rows.append(" | ".join(cells))
    table = "\n".join([header, *rows])
    return (
        f"Source file: outputs/ward_index.csv\n{format_ward_brief(selected, basis)}\n\n"
        "Same wards, with the figures behind those ranks. "
        "Percent columns are already on a 0-100 scale. "
        "shown_failure_rank 1 is the highest sewage-failure pressure. "
        "low_report_rank 1 is the fewest basement-flood reports per eligible home.\n"
        f"{table}"
    )


def _open_chroma():
    return Chroma(
        persist_directory=str(INDEX_DIR),
        embedding_function=LocalEmbeddings(),
        collection_name="flood_policy",
    )


_STORE = None


def _policy_store():
    global _STORE
    if _STORE is not None:
        return _STORE
    stamp = INDEX_DIR / "indexed_from.txt"
    if not INDEX_DIR.exists() or not stamp.exists() or "policy context" not in stamp.read_text(encoding="utf-8"):
        raise SystemExit("Policy index is missing or out of date. Run: python -m rag.build_index")
    try:
        _STORE = _open_chroma()
    except (KeyError, ValueError):
        # A killed client can leave Chroma's process cache pointing at this folder.
        from chromadb.api.shared_system_client import SharedSystemClient

        SharedSystemClient.clear_system_cache()
        _STORE = _open_chroma()
    return _STORE


def _add_docs(found, docs: list, seen: set) -> None:
    for doc in found:
        key = (
            doc.metadata.get("source"),
            doc.metadata.get("page"),
            doc.page_content[:80],
        )
        if key in seen:
            continue
        seen.add(key)
        docs.append(doc)


def _selected_ids(selected: pd.DataFrame) -> set[int]:
    return {int(ward_id) for ward_id in selected["ward_id"].tolist()}


def _doc_ward_ids(text: str) -> set[int]:
    return {int(match) for match in re.findall(r"Ward\s+(\d{1,2})", text)}


def _keep_policy_docs(docs: list, selected: pd.DataFrame) -> list:
    """Prefer pages for the chosen wards, and drop pages that are only about other wards."""
    chosen = _selected_ids(selected)
    names = [str(name).lower() for name in selected["ward_name"].tolist()]
    matched = []
    citywide = []
    for doc in docs:
        text = doc.page_content
        found = _doc_ward_ids(text)
        folded = text.lower()
        about_chosen = bool(found & chosen) or any(name in folded for name in names)
        about_other = bool(found - chosen)
        if about_chosen:
            matched.append(doc)
        elif not about_other:
            citywide.append(doc)
    return matched[:6] + citywide[:2]


def retrieve(question: str, k: int = 5):
    """Return the ward-index block and policy pages for the question."""
    if not WARD_INDEX.exists():
        raise SystemExit(f"Missing {WARD_INDEX}. Run: python -m flood_rag.run")
    scores = pd.read_csv(WARD_INDEX)
    selected, basis = select_wards(scores, question)
    ward_index = _ward_index_context(selected, basis)
    store = _policy_store()
    docs: list = []
    seen: set = set()
    _add_docs(store.similarity_search(question, k=k), docs, seen)

    for _, row in selected.head(3).iterrows():
        query = (
            f"Ward {int(row.ward_id)} {row.ward_name} "
            "basement flooding protection study area subsidy eligibility"
        )
        _add_docs(store.similarity_search(query, k=2), docs, seen)
    return ward_index, _keep_policy_docs(docs, selected)


def generate(question: str, ward_index: str, docs) -> str:
    """Write the answer from a ward-index block and the policy pages already retrieved."""
    if not _ollama_is_up():
        raise SystemExit(
            f"Ollama is not running at {OLLAMA_BASE_URL}. Start it and pull {OLLAMA_MODEL}."
        )
    context = _format_docs(docs) or "No policy pages matched this question."
    model = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
        num_predict=500,
    )
    chain = PROMPT | model | StrOutputParser()
    return chain.invoke({"ward_index": ward_index, "context": context, "question": question})


def answer(question: str, k: int = 5, retrieve_only: bool = False) -> str:
    ward_index, docs = retrieve(question, k=k)
    context = _format_docs(docs) or "No policy pages matched this question."
    if retrieve_only or not _ollama_is_up():
        note = ""
        if not retrieve_only:
            note = (
                f"Ollama is not running at {OLLAMA_BASE_URL}, so this is the retrieved material only.\n"
                f"Start Ollama, pull {OLLAMA_MODEL}, and run the question again.\n\n"
            )
        return f"{note}WARD INDEX\n{ward_index}\n\nPOLICY EXCERPTS\n{context}"
    return generate(question, ward_index, docs)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Query the ward index and policy context PDFs.")
    parser.add_argument("question", nargs="*", help="Question to ask")
    parser.add_argument("--retrieve-only", action="store_true", help="Print sources and do not call Ollama")
    parser.add_argument("-k", type=int, default=5, help="Number of chunks to retrieve")
    args = parser.parse_args(argv)
    question = " ".join(args.question).strip()
    if not question:
        question = input("Question: ").strip()
    if not question:
        raise SystemExit("Provide a question.")
    text = answer(question, k=args.k, retrieve_only=args.retrieve_only)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
