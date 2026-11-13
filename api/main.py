"""Web API over flood_rag.

    python -m uvicorn api.main:app --reload

Interactive docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import AskRequest, AskResponse, Ward
from flood_rag import service
from flood_rag.policy import PolicyIndex, load_passages
from flood_rag.score import build_scores

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Parsing the PDFs is slow, so it happens once, not per request.
    scores = build_scores()
    state["scores"] = scores
    state["wards"] = service.ward_table(scores)
    state["index"] = PolicyIndex(load_passages(), sublinear_tf=True)
    yield
    state.clear()


app = FastAPI(title="Basement flood outreach API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "wards": len(state.get("wards", []))}


@app.get("/api/wards", response_model=list[Ward])
def list_wards():
    return state["wards"]


@app.get("/api/wards/{ward_id}", response_model=Ward)
def get_ward(ward_id: int):
    for ward in state["wards"]:
        if ward["ward_id"] == ward_id:
            return ward
    raise HTTPException(status_code=404, detail=f"No ward {ward_id}. Wards are numbered 1 to 25.")


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest):
    result = service.answer(
        state["scores"],
        state["index"],
        request.question,
        k=request.k,
        model=request.model,
    )
    return AskResponse(
        message_id=uuid.uuid4().hex,
        question=result.question,
        kind=result.kind,
        topic_label=result.topic_label,
        basis=result.basis,
        wards=result.wards,
        passages=[asdict(e) for e in result.passages],
        help=result.help,
        model=result.model,
        answer=result.llm_answer,
        llm_available=result.llm_available,
    )
