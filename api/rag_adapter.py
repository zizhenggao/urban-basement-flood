"""Connect POST /api/ask to the RAG in rag/.

rag.ask gives back text and LangChain documents. The chat needs separate fields,
so this module fills the same AskResponse the chat already reads.
"""

from __future__ import annotations

import logging
import uuid

from api.schemas import AskedWard, AskResponse, Excerpt
from rag import ask as rag_ask
from rag.config import OLLAMA_MODEL

log = logging.getLogger(__name__)


class RagUnavailable(Exception):
    """The ward index or the policy index is missing. The message says what to run."""


def warm_up() -> None:
    """Open Chroma and load the embedding model once, when the API starts.

    A missing index must not stop the API: the map does not need it.
    """
    try:
        rag_ask._policy_store()
    except SystemExit as stop:
        log.warning("Policy index not loaded: %s", stop.code)


def _wards(selected) -> list[AskedWard]:
    wards = []
    for row in selected.itertuples(index=False):
        wards.append(
            AskedWard(
                ward_id=int(row.ward_id),
                ward_name=str(row.ward_name).strip(),
                priority_rank=int(row.priority_rank),
                failure_rank=int(row.shown_failure_rank),
                low_report_rank=int(row.low_report_rank),
                subsidy_participation=float(row.subsidy_participation),
                properties_with_fpd=int(row.properties_with_fpd),
                properties_without_fpd=int(row.properties_without_fpd),
                flood_reports_2019_2022=int(row.flood_reports_2019_2022),
                old_pipe_pct=round(float(row.pct_old_pipe) * 100, 1),
                combined_sewer_pct=round(float(row.pct_combined_sewer) * 100, 1),
            )
        )
    return wards


def _passages(docs) -> list[Excerpt]:
    return [
        Excerpt(
            source=str(doc.metadata.get("source", "unknown")),
            page=int(doc.metadata.get("page") or 0),
            text=doc.page_content.strip(),
        )
        for doc in docs
    ]


def _write_answer(question: str, ward_index: str, docs) -> tuple[str | None, bool]:
    """Ask the model. Returns (text, available). Never raises."""
    if not rag_ask._ollama_is_up():
        return None, False
    try:
        return rag_ask.generate(question, ward_index, docs), True
    except (SystemExit, Exception):  # a stopped or failing model must not turn into a 500
        log.exception("The model did not answer")
        return None, False


def answer(question: str, k: int = 5) -> AskResponse:
    try:
        selected, basis, ward_index, docs = rag_ask.retrieve_parts(question, k=k)
    except SystemExit as stop:
        raise RagUnavailable(str(stop.code)) from stop
    text, available = _write_answer(question, ward_index, docs)
    return AskResponse(
        message_id=uuid.uuid4().hex,
        question=question,
        kind="both",
        topic_label=None,
        basis=basis,
        wards=_wards(selected),
        passages=_passages(docs),
        help=None,
        model=OLLAMA_MODEL,
        answer=text,
        llm_available=available,
    )
