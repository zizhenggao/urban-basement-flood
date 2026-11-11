"""End-to-end checks on the real data and the real PDFs. Slow to start (reads the PDFs)."""

import pytest

from flood_rag import service
from flood_rag.policy import PolicyIndex, load_passages
from flood_rag.score import build_scores


@pytest.fixture(scope="module")
def scores():
    return build_scores()


@pytest.fixture(scope="module")
def index():
    return PolicyIndex(load_passages(), sublinear_tf=True)


def ask(scores, index, question):
    return service.answer(scores, index, question)


def passage_text(result):
    return " ".join(p.text for p in result.passages)


# --- program questions: answered from the PDFs, no ward table ---------------

@pytest.mark.parametrize(
    "question,must_contain",
    [
        ("What does the subsidy cover?", "3,400"),
        ("What is the maximum subsidy per property?", "6,650"),
        ("What is a backwater valve?", "backwater"),
        ("How many applications has the program received?", "59,000"),
    ],
)
def test_program_question_is_answered_from_the_pdfs(scores, index, question, must_contain):
    result = ask(scores, index, question)
    assert result.kind == "program"
    assert result.wards == []
    assert must_contain in passage_text(result)
    assert all(p.page > 0 and p.source for p in result.passages)


def test_general_flooding_question_is_answered_from_the_pdfs(scores, index):
    result = ask(scores, index, "Does rain affect flooding?")
    assert result.kind == "program"
    assert result.wards == []
    assert result.passages


# --- ward questions: answered from the table, no PDF -------------------------

def test_oldest_pipes_ranks_by_old_pipe_share(scores, index):
    result = ask(scores, index, "Where are the oldest pipes?")
    assert (result.kind, result.topic) == ("wards", "old_pipe")
    assert result.passages == []
    first = result.wards[0]["ward_id"]
    assert first == int(scores.loc[scores["pct_old_pipe"].idxmax(), "ward_id"])
    assert [w["topic_rank"] for w in result.wards] == sorted(w["topic_rank"] for w in result.wards)


def test_lowest_subsidy_participation_goes_lowest_first(scores, index):
    result = ask(scores, index, "Which wards have the lowest subsidy participation?")
    assert result.topic == "subsidy"
    first = result.wards[0]["ward_id"]
    assert first == int(scores.loc[scores["subsidy_participation"].idxmin(), "ward_id"])


def test_different_topics_give_different_lists(scores, index):
    lists = {
        topic_q: [w["ward_id"] for w in ask(scores, index, topic_q).wards]
        for topic_q in [
            "Where are the oldest pipes?",
            "Which wards have the most combined sewers?",
            "Which wards have the lowest subsidy participation?",
        ]
    }
    assert len({tuple(v) for v in lists.values()}) == 3


def test_named_wards_are_kept_and_sorted_by_topic(scores, index):
    result = ask(scores, index, "Why might Scarborough wards show low subsidy intake?")
    ids = [w["ward_id"] for w in result.wards]
    assert set(ids) == {20, 21, 22, 23, 24, 25}
    assert [w["topic_rank"] for w in result.wards] == sorted(w["topic_rank"] for w in result.wards)


# --- mixed and unknown -------------------------------------------------------

def test_question_about_a_ward_uses_table_and_pdfs(scores, index):
    result = ask(scores, index, "What should we tell residents in Ward 22?")
    assert result.kind == "both"
    assert 22 in [w["ward_id"] for w in result.wards]
    assert result.passages


def test_readme_outreach_question_keeps_the_outreach_ranking(scores, index):
    q = (
        "Which wards should we outreach because sewer backups are high, few residents "
        "report basement floods, and few homes already have a subsidized device?"
    )
    result = ask(scores, index, q)
    assert result.topic is None
    assert [w["ward_id"] for w in result.wards][:2] == [22, 23]


def test_unknown_question_returns_help_and_no_data(scores, index):
    result = ask(scores, index, "hello")
    assert result.kind == "unknown"
    assert result.wards == [] and result.passages == []
    assert result.help


# --- the 0-100 score used by the map ----------------------------------------

def test_priority_score_and_levels():
    assert service.priority_score(1, 25) == 100
    assert service.priority_score(25, 25) == 0
    assert service.priority_level(70) == "High"
    assert service.priority_level(69) == "Medium"
    assert service.priority_level(40) == "Medium"
    assert service.priority_level(39) == "Low"


def test_ward_table_has_25_wards_in_priority_order(scores):
    table = service.ward_table(scores)
    assert len(table) == 25
    assert [w["priority_rank"] for w in table] == sorted(w["priority_rank"] for w in table)
    levels = [w["level"] for w in table]
    assert (levels.count("High"), levels.count("Medium"), levels.count("Low")) == (8, 7, 10)
