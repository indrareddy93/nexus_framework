"""Embedding engine with in-memory vector store and cosine similarity search."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class SearchResult:
    """A single document retrieval result."""

    id: str
    text: str
    metadata: dict[str, Any]
    score: float


@dataclass
class VectorDocument:
    id: str
    text: str
    metadata: dict[str, Any]
    embedding: list[float]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _simple_tfidf_embedding(text: str, dim: int = 256) -> list[float]:
    """
    Very lightweight deterministic text → vector mapping.
    Used as a fallback when no API key is available.
    Real deployments should use the EmbeddingEngine.embed() which calls OpenAI.
    """
    import hashlib

    h = hashlib.sha256(text.lower().encode()).digest()
    # Turn 32 bytes into 256 floats via cycling
    values: list[float] = []
    for i in range(dim):
        byte_val = h[i % 32]
        char_influence = sum(ord(c) for c in text) % 127
        values.append((byte_val ^ (char_influence + i)) / 255.0)
    # Normalize
    magnitude = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / magnitude for v in values]


class EmbeddingEngine:
    """
    Embedding engine with an in-memory vector store and cosine similarity search.

    Usage::

        embed = EmbeddingEngine()
        await embed.add_documents([
            {"text": "Nexus is an async framework", "metadata": {"source": "docs"}},
        ])
        results = await embed.search("async web framework", top_k=3)
        for r in results:
            print(r.score, r.text)
    """

    def __init__(
        self,
        provider: str = "local",
        model: str = "text-embedding-ada-002",
        api_key: str = "",
        embedding_dim: int = 256,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.embedding_dim = embedding_dim
        self._store: list[VectorDocument] = []

    async def embed(self, text: str) -> list[float]:
        """Compute embedding for a single text string."""
        if self.api_key and self.provider in ("openai", "groq"):
            return await self._embed_openai(text)
        return _simple_tfidf_embedding(text, self.embedding_dim)

    async def _embed_openai(self, text: str) -> list[float]:
        try:
            import httpx
        except ImportError:
            raise ImportError("pip install httpx")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"input": text, "model": self.model}
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["data"][0]["embedding"]

    async def add_documents(self, documents: list[dict[str, Any]]) -> int:
        """Index a list of documents. Each must have a 'text' key."""
        for doc in documents:
            text = doc.get("text", "")
            embedding = await self.embed(text)
            self._store.append(
                VectorDocument(
                    id=doc.get("id", str(uuid.uuid4())),
                    text=text,
                    metadata=doc.get("metadata", {}),
                    embedding=embedding,
                )
            )
        return len(documents)

    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Return the *top_k* most semantically similar documents."""
        if not self._store:
            return []
        q_embedding = await self.embed(query)
        scored: list[tuple[float, VectorDocument]] = []
        for doc in self._store:
            score = _cosine_similarity(q_embedding, doc.embedding)
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchResult(id=doc.id, text=doc.text, metadata=doc.metadata, score=score)
            for score, doc in scored[:top_k]
        ]

    def clear(self) -> None:
        """Remove all indexed documents."""
        self._store.clear()

    @property
    def document_count(self) -> int:
        return len(self._store)
