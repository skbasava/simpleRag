# app/api.py

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.db.postgres import PostgresDriver
from app.db.weaviate import WeaviateDriver
from app.db.weaviate_schema import ensure_schema

from app.rag.router import RAGRouter
from app.rag.service import RAGService
from app.rag.context_resolver import ContextResolver
from app.rag.prompt_builder import PromptBuilder


# ------------------------
# Lifespan
# ------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Infra clients ----
    pg = PostgresDriver()
    wv = WeaviateDriver()

    # ---- Ensure schema ONCE ----
    ensure_schema(wv.client)

    # ---- RAG wiring ----
    router = RAGRouter(pg, wv)
    context_resolver = ContextResolver()
    prompt_builder = PromptBuilder()

    app.state.rag = RAGService(
        router=router,
        context_resolver=context_resolver,
        prompt_builder=prompt_builder,
    )

    yield

    # ---- Cleanup (optional) ----
    wv.client.close()


app = FastAPI(lifespan=lifespan)


# ------------------------
# API endpoints
# ------------------------

@app.post("/query")
async def query(payload: dict):
    """
    payload = { "query": "<user text>" }
    """
    user_query = payload.get("query", "").strip()

    if not user_query:
        return {
            "answer": "Query cannot be empty.",
            "needs_context": False,
        }

    rag = app.state.rag
    result = await rag.answer(user_query)

    return result


@app.get("/health")
async def health():
    return {"status": "ok"}