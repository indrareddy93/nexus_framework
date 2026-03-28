"""RAG Pipeline — Retrieval-Augmented Generation made simple."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.ai.engine import AIEngine
from nexus.ai.embeddings import EmbeddingEngine, SearchResult


@dataclass
class RAGResponse:
    answer: str
    sources: list[SearchResult]
    model: str
    usage: dict[str, int]


class RAGPipeline:
    """
    End-to-end RAG pipeline: embed documents, retrieve relevant context,
    generate grounded answers.

    Usage::

        rag = RAGPipeline(
            ai=AIEngine(api_key="sk-..."),
            embeddings=EmbeddingEngine(api_key="sk-..."),
        )

        await rag.ingest([
            {"text": "Nexus supports async-first architecture.", "metadata": {"source": "docs"}},
            {"text": "The ORM layer handles SQL via query builder.", "metadata": {"source": "docs"}},
        ])

        result = await rag.query("What databases does Nexus support?")
        print(result.answer)
        for src in result.sources:
            print(src.score, src.text)
    """

    DEFAULT_TEMPLATE = (
        "Answer the question based strictly on the provided context. "
        "If the context doesn't contain enough information, say so clearly.\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}\n\n"
        "Answer:"
    )

    def __init__(
        self,
        ai: AIEngine,
        embeddings: EmbeddingEngine,
        prompt_template: str | None = None,
        top_k: int = 5,
    ) -> None:
        self.ai = ai
        self.embeddings = embeddings
        self.template = prompt_template or self.DEFAULT_TEMPLATE
        self.top_k = top_k

    async def ingest(self, documents: list[dict[str, Any]]) -> int:
        """Add documents to the knowledge base. Returns count added."""
        return await self.embeddings.add_documents(documents)

    async def query(self, question: str, top_k: int | None = None) -> RAGResponse:
        """Retrieve relevant context and generate a grounded answer."""
        k = top_k or self.top_k
        sources = await self.embeddings.search(question, top_k=k)

        context = "\n\n".join(f"[{i+1}] {s.text}" for i, s in enumerate(sources))
        prompt = self.template.format(context=context, question=question)
        response = await self.ai.generate(prompt)

        return RAGResponse(
            answer=response.content,
            sources=sources,
            model=response.model,
            usage=response.usage,
        )

    def clear_knowledge_base(self) -> None:
        """Remove all indexed documents."""
        self.embeddings.clear()

    @property
    def document_count(self) -> int:
        return self.embeddings.document_count
