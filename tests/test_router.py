import pytest

from flood_rag.router import classify, detect_topic

# (question, names a ward, expected kind, expected topic)
CASES = [
    ("What does the subsidy cover?", False, "program", None),
    ("What is a backwater valve?", False, "program", None),
    ("Who can apply for the subsidy?", False, "program", None),
    ("What is the maximum subsidy per property?", False, "program", None),
    ("How many applications has the program received?", False, "program", None),
    ("Where are the oldest pipes?", False, "wards", "old_pipe"),
    ("Which wards have the highest sewage-failure pressure?", False, "wards", None),
    ("Which wards have the most combined sewers?", False, "wards", "combined"),
    ("Where are sewer backups highest?", False, "wards", "backup"),
    ("Which wards have the most tree roots over pipes?", False, "wards", "roots"),
    ("Which wards have the most flood reports?", False, "wards", "reports"),
    ("Which wards have the lowest subsidy participation?", False, "wards", "subsidy"),
    ("Why might Scarborough wards show low subsidy intake?", True, "wards", "subsidy"),
    ("What should we tell residents in Ward 22?", True, "both", None),
    ("Where should we focus outreach first?", False, "wards", None),
    (
        "Which wards should we outreach because sewer backups are high, few residents "
        "report basement floods, and few homes already have a subsidized device?",
        False,
        "both",
        None,
    ),
    ("hello", False, "unknown", None),
    ("What is the weather today?", False, "unknown", None),
    # General flooding questions go to the documents.
    ("Does rain affect flooding?", False, "program", None),
    ("the rainning affect the flooding??", False, "program", None),
    ("What causes basement flooding?", False, "program", None),
    ("Does heavy rain cause basement flooding?", False, "program", None),
    ("How do storms affect basement flooding?", False, "program", None),
    # Known limit: "sewer" and "pipes" count as ward words, so this one is read as a ward question.
    ("How do storms affect sewer capacity?", False, "wards", None),
]


@pytest.mark.parametrize("question,names_ward,kind,topic", CASES)
def test_kind_and_topic(question, names_ward, kind, topic):
    assert classify(question, names_ward) == kind
    assert detect_topic(question) == topic


def test_several_topics_in_one_question_pick_none():
    # Backups, reports and subsidy together mean the outreach ranking, not one column.
    q = "Where are sewer backups high, few flood reports and low subsidy participation?"
    assert detect_topic(q) is None
