"""Web API over flood_rag.

    python -m uvicorn api.main:app --reload

Interactive docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api import rag_adapter
from api.schemas import AskRequest, AskResponse, Ward
from flood_rag import service
from flood_rag.score import build_scores

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The map still reads the ward scores from flood_rag.
    scores = build_scores()
    state["scores"] = scores
    state["wards"] = service.ward_table(scores)
    # Chroma and the embedding model load once here, not on every question.
    rag_adapter.warm_up()
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
    try:
        return rag_adapter.answer(request.question, k=request.k)
    except rag_adapter.RagUnavailable as problem:
        raise HTTPException(status_code=503, detail=str(problem))
