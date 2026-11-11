from __future__ import annotations

from pydantic import BaseModel, Field


class Factor(BaseModel):
    label: str
    detail: str


class Ward(BaseModel):
    ward_id: int
    ward_name: str
    priority_rank: int = Field(description="1 = strongest outreach case, 25 = weakest")
    score: int = Field(description="0-100, derived from the rank. An order, not a probability")
    level: str = Field(description="High (70+), Medium (40-69) or Low (below 40)")
    top_factors: list[Factor]
    failure_rank: int = Field(description="1 = highest sewage-failure pressure")
    low_report_rank: int = Field(description="1 = fewest flood reports per eligible home")
    subsidy_participation: float = Field(description="Share of eligible homes with a device, 0-1")
    eligible_homes: int
    properties_without_fpd: int
    flood_reports_2019_2022: int


class AskedWard(BaseModel):
    ward_id: int
    ward_name: str
    priority_rank: int
    failure_rank: int
    low_report_rank: int
    subsidy_participation: float
    properties_with_fpd: int
    properties_without_fpd: int
    flood_reports_2019_2022: int
    topic_rank: int | None = Field(default=None, description="Rank on the asked topic, when the question had one")
    topic_value: str | None = Field(default=None, description="The ward's value on that topic, in plain language")


class Excerpt(BaseModel):
    source: str
    page: int
    ward_id: int | None
    score: float
    text: str


class HistoryTurn(BaseModel):
    role: str = Field(description="'user' or 'assistant'")
    content: str


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    model: str = Field(default="", description="Ollama model name. Empty means do not use a model")
    k: int = Field(default=4, ge=1, le=10)
    history: list[HistoryTurn] = Field(
        default_factory=list,
        description="Reserved for conversation memory. Not used yet",
    )


class AskResponse(BaseModel):
    message_id: str
    question: str
    kind: str = Field(description="program, wards, both or unknown")
    topic_label: str | None = Field(description="Ward-table topic the question was about, if one")
    basis: str
    wards: list[AskedWard]
    passages: list[Excerpt] = Field(description="Short passages from the program PDFs")
    help: str | None = Field(description="Set when the question was not understood")
    model: str
    answer: str | None = Field(description="Text from the local model, or null")
    llm_available: bool | None = Field(
        description="null: no model requested. true: it answered. false: Ollama did not respond"
    )
