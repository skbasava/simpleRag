"""
LibreChat → Unified RAG Middleware
---------------------------------
Always calls POST /query
"""

import re
import requests
from typing import Optional, Dict, Any, List
from fastapi import FastAPI
from pydantic import BaseModel

RAG_QUERY_URL = "http://localhost:9000/query"
LIBRECHAT_API_URL = "http://localhost:3080/api/chat"
DEFAULT_PROJECT = "AMBOSELI"

app = FastAPI(title="LibreChat Unified RAG Middleware")


class ChatRequest(BaseModel):
    user_query: str
    project: Optional[str] = None
    mpu_name: Optional[str] = None
    profile: Optional[str] = None
    limit: int = 5
    session_id: Optional[str] = None


HEX_PATTERN = re.compile(r"0x[0-9A-Fa-f]+")


def extract_address_range(text: str):
    matches = HEX_PATTERN.findall(text)
    if len(matches) >= 2:
        return {"start_hex": matches[0], "end_hex": matches[1]}
    return None


def build_context(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "NO RELEVANT POLICIES FOUND."
    return "\n\n---\n\n".join(r["chunk_text"] for r in results)


def build_prompt(context: str, question: str) -> str:
    return f"""
You are a security policy assistant.
You MUST answer using ONLY the context below.
If the answer is not present, respond with:
"Not found in active policy database."

======================
CONTEXT
======================
{context}

======================
USER QUESTION
======================
{question}
""".strip()


@app.post("/chat")
def chat(req: ChatRequest):
    project = req.project or DEFAULT_PROJECT

    addr = extract_address_range(req.user_query)

    if addr:
        payload = {
            "project": project,
            "mode": "ADDRESS",
            "address_range": addr,
        }
    else:
        payload = {
            "project": project,
            "mode": "SEMANTIC",
            "semantic_query": req.user_query,
            "limit": req.limit,
        }

        if req.mpu_name:
            payload["mpu_name"] = req.mpu_name
        if req.profile:
            payload["profile"] = req.profile

    rag_resp = requests.post(RAG_QUERY_URL, json=payload, timeout=30)
    rag_resp.raise_for_status()
    rag_data = rag_resp.json()

    results = rag_data.get("results", [])

    context = build_context(results)
    final_prompt = build_prompt(context, req.user_query)

    libre_payload = {
        "prompt": final_prompt,
        "session_id": req.session_id,
    }

    llm_resp = requests.post(LIBRECHAT_API_URL, json=libre_payload, timeout=60)
    llm_resp.raise_for_status()

    return {
        "project": project,
        "rag_mode": rag_data.get("mode"),
        "rag_hits": rag_data.get("hit_count"),
        "llm_response": llm_resp.json(),
    }