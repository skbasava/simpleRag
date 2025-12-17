# rag/models.py

from pydantic import BaseModel
from typing import Optional, List


# -------------------------
# Incoming API request
# -------------------------
class RAGQueryRequest(BaseModel):
    query: str
    project: Optional[str] = None
    version: Optional[str] = None
    top_k: int = 5
    stream: bool = False


# -------------------------
# K-shot rewritten query
# -------------------------
class RewrittenQuery(BaseModel):
    original_query: str
    rewritten_query: str
    inferred_project: Optional[str] = None
    inferred_version: Optional[str] = None


# -------------------------
# Vector search hit
# -------------------------
class VectorHit(BaseModel):
    vector_id: str
    score: float


# -------------------------
# DB chunk payload
# -------------------------
class RetrievedChunk(BaseModel):
    chunk_text: str
    project: str
    version: str
    profile: str
    mpu_name: str
    rg_index: int
    chunk_index: int
    score: float


# -------------------------
# Final RAG response
# -------------------------
class RAGAnswer(BaseModel):
    answer: str
    citations: List[RetrievedChunk]