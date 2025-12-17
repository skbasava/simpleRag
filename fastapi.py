from fastapi import FastAPI, HTTPException
from app.api.models import QueryRequest, QueryResponse, SourceChunk
from app.rag.router import RAGRouter


def create_app(rag_router: RAGRouter) -> FastAPI:
    app = FastAPI(
        title="Policy RAG API",
        version="1.0",
    )

    @app.post("/query", response_model=QueryResponse)
    async def query_endpoint(req: QueryRequest):
        # 1️⃣ Validate required context
        if not req.project or not req.version:
            raise HTTPException(
                status_code=400,
                detail="Both 'project' and 'version' are required",
            )

        # 2️⃣ Call router → RAGService
        result = await rag_router.query(
            query=req.query,
            project=req.project,
            version=req.version,
        )

        # 3️⃣ Adapt internal chunks → API schema
        sources = [
            SourceChunk(
                chunk_id=c.chunk_id,
                mpu_name=c.mpu_name,
                rg_index=c.rg_index,
                profile=c.profile,
                start_hex=c.start_hex,
                end_hex=c.end_hex,
            )
            for c in result.sources
        ]

        return QueryResponse(
            answer=result.answer,
            confidence=result.confidence,
            sources=sources,
        )

    return app