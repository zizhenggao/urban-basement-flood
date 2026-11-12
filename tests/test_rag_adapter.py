"""The adapter turns rag.ask output into the AskResponse the chat reads.

The search and the model are replaced by fakes, so no Ollama or Chroma is needed.
The ward rows are the real ones from outputs/ward_index.csv.
"""

from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException

from api import main, rag_adapter
from api.schemas import AskRequest
from flood_rag.score import select_wards
from rag.config import OLLAMA_MODEL, WARD_INDEX

QUESTION = "Which ward has the highest share of old sewer pipes?"


def _doc(source, page, text):
    return SimpleNamespace(metadata={"source": source, "page": page}, page_content=text)


@pytest.fixture
def parts():
    scores = pd.read_csv(WARD_INDEX)
    selected, basis = select_wards(scores, QUESTION)
    docs = [
        _doc("Basement Flooding Protection Program Summary .pdf", 10, "  Ward 10: Spadina-Fort York  "),
        _doc("Basement Flooding Protection Program Status Update .pdf", 6, "Legend text"),
    ]
    return selected, basis, "ward index text", docs


@pytest.fixture
def fake_rag(monkeypatch, parts):
    calls = {"generate": 0}

    def generate(question, ward_index, docs):
        calls["generate"] += 1
        return "MODEL TEXT"

    monkeypatch.setattr(rag_adapter.rag_ask, "retrieve_parts", lambda question, k=5: parts)
    monkeypatch.setattr(rag_adapter.rag_ask, "_ollama_is_up", lambda: True)
    monkeypatch.setattr(rag_adapter.rag_ask, "generate", generate)
    return calls


def test_fills_every_field(fake_rag):
    result = rag_adapter.answer(QUESTION)
    assert result.answer == "MODEL TEXT"
    assert result.llm_available is True
    assert result.model == OLLAMA_MODEL
    assert result.question == QUESTION
    assert result.help is None
    assert len(result.message_id) == 32


def test_ward_rows_carry_the_pipe_columns(fake_rag):
    result = rag_adapter.answer(QUESTION)
    assert len(result.wards) == 5
    st_pauls = next(w for w in result.wards if w.ward_id == 12)
    assert st_pauls.ward_name == "Toronto-St. Paul's"
    assert st_pauls.old_pipe_pct == 60.7
    assert st_pauls.combined_sewer_pct == 47.2
    assert st_pauls.failure_rank == 5
    assert 0 <= st_pauls.subsidy_participation <= 1


def test_passages_copy_source_page_and_text(fake_rag):
    result = rag_adapter.answer(QUESTION)
    assert [p.page for p in result.passages] == [10, 6]
    assert result.passages[0].source.startswith("Basement Flooding Protection Program Summary")
    assert result.passages[0].text == "Ward 10: Spadina-Fort York"


def test_ollama_down_still_returns_the_data(monkeypatch, fake_rag):
    monkeypatch.setattr(rag_adapter.rag_ask, "_ollama_is_up", lambda: False)
    result = rag_adapter.answer(QUESTION)
    assert result.answer is None
    assert result.llm_available is False
    assert len(result.wards) == 5
    assert fake_rag["generate"] == 0


def test_model_failure_does_not_raise(monkeypatch, fake_rag):
    def broken(question, ward_index, docs):
        raise SystemExit("Ollama stopped")

    monkeypatch.setattr(rag_adapter.rag_ask, "generate", broken)
    result = rag_adapter.answer(QUESTION)
    assert result.answer is None
    assert result.llm_available is False


def test_missing_index_becomes_rag_unavailable(monkeypatch):
    def missing(question, k=5):
        raise SystemExit("Policy index is missing or out of date. Run: python -m rag.build_index")

    monkeypatch.setattr(rag_adapter.rag_ask, "retrieve_parts", missing)
    with pytest.raises(rag_adapter.RagUnavailable, match="rag.build_index"):
        rag_adapter.answer(QUESTION)


def test_endpoint_answers_503_when_the_index_is_missing(monkeypatch):
    def unavailable(question, k=5):
        raise rag_adapter.RagUnavailable("Run: python -m rag.build_index")

    monkeypatch.setattr(main.rag_adapter, "answer", unavailable)
    with pytest.raises(HTTPException) as problem:
        main.ask(AskRequest(question=QUESTION))
    assert problem.value.status_code == 503
    assert "rag.build_index" in problem.value.detail
