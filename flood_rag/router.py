"""Decide what a question is about. Keyword rules, English only.

classify() says whether to answer from the ward table, the program PDFs, both,
or neither. detect_topic() picks one of six ward-table topics when the
question is about exactly one of them.
"""

from __future__ import annotations

import re

# Words about the program itself (what it pays for, who can use it, how it works).
_PROGRAM = re.compile(
    r"\b(subsid\w*|cover\w*|eligib\w*|valves?|sump\w*|weeping|apply|applying|applications?|"
    r"cost\w*|how much|grants?|programs?|bfpp\w*|plumb\w*|battery|install\w*|fund\w*|"
    r"budget\w*|capital plan|projects?|devices?|reimburs\w*|rebates?|what is (a|an)|"
    r"tell|message|residents|homeowners|owners)\b",
    re.I,
)

# Words about where things are, or how wards compare.
_WARDS = re.compile(
    r"\b(wards?|neighbou?rhoods?|districts?|areas?|where (are|is|should|do|does)|"
    r"highest|lowest|most|least|top \d+|rank\w*|priorit\w*|outreach|focus|target\w*|"
    r"old(er|est)?|ag(e|ing)|pipes?|sewers?|sewage|back-?ups?|combined|roots?|trees?|"
    r"report(s|ed|ing)?|complaints?|311|participation|intake|uptake|take-?up|"
    r"failure|pressure)\b",
    re.I,
)

# Words about flooding in general (what causes it, how rain affects it). They only decide
# the answer when the question has no program or ward words, so "flood reports" in a ward
# question is not pulled toward the PDFs. "rain\w*" also catches misspellings like "rainning".
_GENERAL = re.compile(
    r"\b(rain\w*|storms?|climate|precipitation|caus(e|es|ed|ing)|flood\w*|basements?|"
    r"capacity|groundwater|inflow|infiltration|prevent\w*|protect\w*|damage\w*)\b",
    re.I,
)

# "subsidy" next to these words is about uptake in the table, not about the program rules.
_SUBSIDY_UPTAKE = re.compile(
    r"\b(participation|intake|uptake|take-?up|subsidi[sz]ed|device share|"
    r"without (a )?(flood )?(protection )?devices?|low subsid\w*)\b",
    re.I,
)

TOPIC_PATTERNS = {
    "old_pipe": re.compile(r"\bold(er|est)?\b|\bag(e|ing)\b", re.I),
    "combined": re.compile(r"\bcombined\b", re.I),
    "backup": re.compile(r"\bback-?ups?\b|\bbacked up\b", re.I),
    "roots": re.compile(r"\broots?\b|\btrees?\b", re.I),
    "reports": re.compile(r"\breport(s|ed|ing)?\b|\bcomplaints?\b|\b311\b", re.I),
    "subsidy": _SUBSIDY_UPTAKE,
}

HELP = (
    "I can answer two kinds of questions. "
    "About the program: what the subsidy covers, who can apply, what a backwater valve or sump pump is. "
    "About flooding: what causes basement flooding, how rain and storms affect it. "
    "About the wards: where sewer pipes are oldest, where combined sewers or sewer backups are highest, "
    "where tree roots or flood reports are highest, and where few homes have a subsidized device. "
    "Try: \"What does the subsidy cover?\" or \"Where are the oldest pipes?\""
)


def detect_topic(question: str) -> str | None:
    """The one ward-table topic the question is about, or None if zero or several."""
    found = [name for name, rx in TOPIC_PATTERNS.items() if rx.search(question)]
    return found[0] if len(found) == 1 else None


def classify(question: str, names_a_ward: bool = False) -> str:
    """'program', 'wards', 'both' or 'unknown'."""
    uptake = bool(_SUBSIDY_UPTAKE.search(question))
    # "subsidy intake" is a ward topic; do not let the word "subsidy" count as a program word then.
    program_text = re.sub(r"\bsubsid\w*", " ", question, flags=re.I) if uptake else question
    program = bool(_PROGRAM.search(program_text))
    wards = names_a_ward or bool(_WARDS.search(question))
    if program and wards:
        return "both"
    if program:
        return "program"
    if wards:
        return "wards"
    if _GENERAL.search(question):
        return "program"  # general flooding questions are answered from the documents
    return "unknown"
