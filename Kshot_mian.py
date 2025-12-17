# app/main.py

import logging

from app.db.postgres import PostgresDriver
from app.db.weaviate import WeaviateDriver
from app.db.weaviate_schema import ensure_schema

from app.embedder.embedder import Embedder
from app.llm.groq_client import GroqClient

from app.rag.semantic_search import SemanticSearcher
from app.rag.structured_search import StructuredSearcher
from app.rag.kshot import KShotRewriter
from app.rag.prompt_builder import PromptBuilder
from app.rag.rank import HybridRanker
from app.rag.service import RAGService
from app.rag.router import RAGRouter

from app.api import create_app


log = logging.getLogger(__name__)


def build_rag_service() -> RAGService:
    """
    Composition root for RAG.
    This is the ONLY place objects are created and wired.
    """

    # -----------------------------
    # Infrastructure
    # -----------------------------
    pg = PostgresDriver()
    pg.connect()

    wv = WeaviateDriver()
    ensure_schema(wv.client)

    embedder = Embedder()
    llm_client = GroqClient()

    # -----------------------------
    # Search layers
    # -----------------------------
    semantic_searcher = SemanticSearcher(
        weaviate_client=wv,
        embedder=embedder,
    )

    structured_searcher = StructuredSearcher(
        pg=pg,
    )

    # -----------------------------
    # Intelligence layers
    # -----------------------------
    kshot = KShotRewriter(
        examples_path="/app/data/kshot_examples.yaml",
        min_confidence=0.6,
    )

    prompt_builder = PromptBuilder()

    ranker = HybridRanker(
        semantic_weight=0.6,
        structured_weight=0.4,
    )

    # -----------------------------
    # RAG Service
    # -----------------------------
    rag_service = RAGService(
        semantic_searcher=semantic_searcher,
        structured_searcher=structured_searcher,
        llm_client=llm_client,
        kshot=kshot,
        prompt_builder=prompt_builder,
        ranker=ranker,
    )

    return rag_service


def main():
    log.info("Starting RAG application")

    rag_service = build_rag_service()

    rag_router = RAGRouter(
        rag_service=rag_service
    )

    app = create_app(rag_router)

    return app


# FastAPI entrypoint
app = main()