"""Score the ward RAG with RAGAS and store the run in MLflow.

The judge is the local Ollama model, so the ward table is not sent to a paid API.
Faithfulness checks the answer against the ward index and the policy pages.
Answer relevancy checks that the paragraph addresses the question.
Factual correctness compares it with the expected ward-index facts.

    .\\.venv-rag\\Scripts\\python -m rag.evaluate
    .\\.venv-rag\\Scripts\\mlflow ui --backend-store-uri sqlite:///mlflow.db
"""

from __future__ import annotations

import os
import sys
import types

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION", "True")
os.environ.setdefault("MLFLOW_GENAI_EVAL_LLM_TIMEOUT", "180")


def _allow_ragas_import() -> None:
    """Current RAGAS imports Vertex classes that this LangChain build no longer ships.

    The classes are only used to recognize a Vertex model. A local stand-in keeps
    the import working for the Ollama judge.
    """
    import langchain_community.chat_models  # noqa: F401
    import langchain_community.llms  # noqa: F401

    chat_name = "langchain_community.chat_models.vertexai"
    if chat_name not in sys.modules:
        chat = types.ModuleType(chat_name)

        class ChatVertexAI:
            pass

        chat.ChatVertexAI = ChatVertexAI
        sys.modules[chat_name] = chat

    llm_name = "langchain_community.llms.vertexai"
    if llm_name not in sys.modules:
        llm = types.ModuleType(llm_name)

        class VertexAI:
            pass

        llm.VertexAI = VertexAI
        sys.modules[llm_name] = llm


_allow_ragas_import()

import mlflow
from mlflow.entities import SpanType
from mlflow.genai.scorers.ragas import AnswerRelevancy, Faithfulness, FactualCorrectness

from ragas.embeddings.base import BaseRagasEmbedding

from rag.ask import generate, retrieve
from rag.config import OLLAMA_BASE_URL, OLLAMA_MODEL, ROOT
from rag.embeddings import LocalEmbeddings


class LocalRagasEmbeddings(BaseRagasEmbedding):
    """Same local bge-small model the retriever uses. No OpenAI key."""

    def __init__(self) -> None:
        super().__init__()
        self._embeddings = LocalEmbeddings()

    def embed_text(self, text: str, **kwargs) -> list[float]:
        return self._embeddings.embed_query(text)

    async def aembed_text(self, text: str, **kwargs) -> list[float]:
        return self.embed_text(text)

JUDGE_MODEL = f"ollama:/{OLLAMA_MODEL}"

# Expected facts are the ward-index numbers a correct answer has to carry.
CASES = [
    {
        "question": (
            "Which wards should we outreach, and what does the subsidy program offer them?"
        ),
        "expected_answer": (
            "Ward 22 Scarborough-Agincourt is priority rank 1 of 25. "
            "2.0% of its eligible homes already have a subsidized flood device, "
            "and 15063 homes are still without one. "
            "Ward 23 Scarborough North is priority rank 2. "
            "1.1% of its eligible homes have a device, and 17593 homes are without one."
        ),
        "must_mention": ["22", "Scarborough-Agincourt", "15063", "23", "17593"],
    },
    {
        "question": "How many homes in Ward 22 still do not have a subsidized flood device?",
        "expected_answer": (
            "Ward 22 Scarborough-Agincourt has 15063 homes without a subsidized flood device."
        ),
        "must_mention": ["22", "15063"],
    },
]


def _contexts(ward_index: str, docs) -> list[str]:
    """Keep the judge's context inside the local model's window."""
    pages = []
    for doc in docs[:3]:
        source = doc.metadata.get("source", "policy")
        page = doc.metadata.get("page")
        where = f"{source} p.{page}" if page else str(source)
        pages.append(f"{where}\n{doc.page_content[:1200]}")
    return [f"outputs/ward_index.csv\n{ward_index[:2500]}", *pages]


def _term_hit(answer: str, terms: list[str]) -> float:
    folded = answer.lower().replace(",", "")
    if not terms:
        return 1.0
    found = sum(1 for term in terms if term.lower().replace(",", "") in folded)
    return found / len(terms)


ANSWERS: dict[str, str] = {}


@mlflow.trace(span_type=SpanType.CHAIN)
def traced_rag_predict(question: str) -> dict:
    """Run one question. The retriever span is what RAGAS faithfulness reads."""
    with mlflow.start_span(name="retriever", span_type=SpanType.RETRIEVER) as span:
        ward_index, docs = retrieve(question)
        contexts = _contexts(ward_index, docs)
        span.set_inputs({"question": question})
        span.set_outputs([{"content": text} for text in contexts])

    with mlflow.start_span(name="generator", span_type=SpanType.LLM) as span:
        response = generate(question, ward_index, docs)
        span.set_inputs({"question": question})
        span.set_outputs(response)

    ANSWERS[question] = response
    return response


def main() -> None:
    os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_BASE_URL)
    tracking_db = (ROOT / "mlflow.db").resolve().as_posix()
    mlflow.set_tracking_uri(f"sqlite:///{tracking_db}")
    mlflow.autolog(disable=True)
    mlflow.set_experiment("ward-rag")

    data = [
        {
            "inputs": {"question": case["question"]},
            "expectations": {"expected_output": case["expected_answer"]},
        }
        for case in CASES
    ]
    local_embeddings = LocalRagasEmbeddings()
    scorers = [
        Faithfulness(model=JUDGE_MODEL),
        AnswerRelevancy(model=JUDGE_MODEL, embeddings=local_embeddings),
        FactualCorrectness(model=JUDGE_MODEL),
    ]

    with mlflow.start_run(run_name="ragas-ward-index"):
        mlflow.log_params(
            {
                "generator": OLLAMA_MODEL,
                "judge": JUDGE_MODEL,
                "questions": len(CASES),
                "sources": "policy context + outputs/ward_index.csv",
            }
        )
        results = mlflow.genai.evaluate(
            data=data,
            predict_fn=traced_rag_predict,
            scorers=scorers,
        )
        hits = []
        for case in CASES:
            response = ANSWERS.get(case["question"], "")
            hits.append(_term_hit(response, case["must_mention"]))
            print("\n" + case["question"])
            print(response)
        mlflow.log_metric("index_terms_present", sum(hits) / len(hits))
        print(f"\nindex_terms_present={sum(hits) / len(hits):.2f}")
        print(results)
        print(f"\nMLflow run: {mlflow.active_run().info.run_id}")
        print("View it with: .\\.venv-rag\\Scripts\\mlflow ui --backend-store-uri sqlite:///mlflow.db")


if __name__ == "__main__":
    main()
