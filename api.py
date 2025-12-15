# api.py
from fastapi import FastAPI
from pydantic import BaseModel
from router import RAGRouter
from rag.prompt_builder import build_prompt

app = FastAPI()
router = RAGRouter()


class QueryRequest(BaseModel):
    query: str
    project: str | None = None
    mpu: str | None = None
    profile: str | None = None
    version: str | None = None


@app.post("/rag/query")
async def rag_query(req: QueryRequest):
    filters = {
        "project": req.project,
        "mpu": req.mpu,
        "profile": req.profile,
    }

    qtype, context = router.route(req.query, filters)

    prompt = build_prompt(
        user_query=req.query,
        context_chunks=context,
        project=req.project,
        version=req.version,
    )

    return {
        "query_type": qtype,
        "context_chunks": len(context),
        "prompt": prompt,
    }
