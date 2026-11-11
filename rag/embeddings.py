"""Local embeddings through FastEmbed. No torch install."""

from langchain_core.embeddings import Embeddings

from rag.config import EMBED_MODEL


class LocalEmbeddings(Embeddings):
    def __init__(self, model_name: str = EMBED_MODEL):
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        vector = next(self._model.embed([text]))
        return vector.tolist()
