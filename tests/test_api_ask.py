"""POST /api/ask on the flood_rag path. No model is asked, so Ollama is not needed."""

import pytest

from api import main
from api.schemas import AskRequest
from flood_rag import service
from flood_rag.policy import PolicyIndex, load_passages
from flood_rag.score import build_scores


@pytest.fixture(scope="module", autouse=True)
def loaded():
    scores = build_scores()
    main.state["scores"] = scores
    main.state["wards"] = service.ward_table(scores)
    main.state["index"] = PolicyIndex(load_passages(), sublinear_tf=True)
    yield
    main.state.clear()


def _ask(question):
    return main.ask(AskRequest(question=question))


def test_oldest_pipes_puts_ward_12_first():
    result = _ask("Which ward has the highest share of old sewer pipes?")
    assert [w.ward_id for w in result.wards[:3]] == [12, 4, 11]
    assert result.llm_available is None


def test_combined_sewer_puts_ward_11_first():
    result = _ask("Which ward has the highest share of combined sewer?")
    assert [w.ward_id for w in result.wards[:3]] == [11, 9, 13]


def test_program_question_returns_passages_and_no_wards():
    result = _ask("What does the subsidy cover?")
    assert result.kind == "program"
    assert result.wards == []
    assert result.passages


def test_off_topic_question_returns_help():
    result = _ask("What is the weather today?")
    assert result.kind == "unknown"
    assert result.help
