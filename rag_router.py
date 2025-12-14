from fastapi import FastAPI, Request
from pydantic import BaseModel
import re
import requests
import psycopg2
import os
import json

app = FastAPI()

# -----------------------------
# Postgres Config
# -----------------------------
PG = {
    "host": os.getenv("PG_HOST", "rag-postgres"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "user": os.getenv("PG_USER", "raguser"),
    "password": os.getenv("PG_PASSWORD", "ragpass"),
    "db": os.getenv("PG_DB", "ragdb")
}

def pg_connect():
    return psycopg2.connect(
        host=PG["host"],
        port=PG["port"],
        user=PG["user"],
        password=PG["password"],
        dbname=PG["db"]
    )

# -----------------------------
# Weaviate Config
# -----------------------------
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
WEAVIATE_CLASS = "AccessControlPolicy"


# -----------------------------
# Query Classifier
# -----------------------------
def classify_query(q: str) -> str:

    q_lower = q.lower()

    # STRUCTURED QUERIES
    structured_keywords = [
        "mpu", "project", "version", "v5", "v4", "list",
        "show", "compare", "diff", "start", "end", "0x",
        "chunk", "prtn", "rg", "address", "range"
    ]

    if any(k in q_lower for k in structured_keywords):
        # Check if semantic hints also exist
        if "similar" in q_lower or "semantic" in q_lower or "meaning" in q_lower:
            return "hybrid"
        return "structured"

    # SEMANTIC QUERIES
    semantic_keywords = [
        "similar", "meaning", "describe", "explain",
        "policy related to", "rationale", "text like",
        "modem", "debug", "test", "security reason"
    ]

    if any(k in q_lower for k in semantic_keywords):
        return "semantic"

    # DEFAULT = semantic
    return "semantic"


# -----------------------------
# VECTOR SEARCH (Weaviate)
# -----------------------------
def vector_search(query: str, top_k=10):
    payload = {
        "class": WEAVIATE_CLASS,
        "query": query,
        "limit": top_k
    }
    r = requests.post(f"{WEAVIATE_URL}/v1/graphql", json={
        "query": f"""
        {{
            Get {{
                {WEAVIATE_CLASS}(nearText: {{ concepts: [\"{query}\"] }}, limit: {top_k}) {{
                    chunk_text
                    project
                    mpu_name
                    profile
                    rg_index
                }}
            }}
        }}
        """
    })
    return r.json()


# -----------------------------
# STRUCTURED SEARCH (Postgres)
# -----------------------------
def postgres_structured_search(query: str):
    conn = pg_connect()
    cur = conn.cursor()

    # Address range query detection
    hex_match = re.findall(r"0x[0-9a-fA-F]+", query)
    address = int(hex_match[0], 16) if hex_match else None

    # MPU name detection
    mpu_match = re.findall(r"mpu\s+([A-Za-z0-9_]+)", query.lower())

    # Build SQL
    sql = "SELECT project,mpu_name,rg_index,profile,start_hex,end_hex,chunk_text FROM policy_chunks WHERE is_active=TRUE"

    conditions = []
    params = []

    if address:
        conditions.append("start_dec <= %s AND end_dec >= %s")
        params.extend([address, address])

    if mpu_match:
        conditions.append("LOWER(mpu_name) = LOWER(%s)")
        params.append(mpu_match[0])

    if conditions:
        sql += " AND " + " AND ".join(conditions)

    cur.execute(sql, params)
    rows = cur.fetchall()

    cur.close()
    conn.close()
    return rows


# -----------------------------
# HYBRID SEARCH
# -----------------------------
def hybrid_search(query: str):
    # Step 1: vector candidates
    v = vector_search(query)
    # Step 2: filter using structured Postgres constraints
    p = postgres_structured_search(query)

    # Rerank / intersect by MPU, project, version
    structured_texts = [r[6] for r in p]

    hybrid_results = []
    for obj in v["data"]["Get"][WEAVIATE_CLASS]:
        if obj["chunk_text"] in structured_texts:
            hybrid_results.append(obj)

    return hybrid_results


# -----------------------------
# MAIN RAG ENDPOINT
# -----------------------------
class QueryRequest(BaseModel):
    query: str


@app.post("/rag/query")
def rag_query(req: QueryRequest):

    q = req.query
    mode = classify_query(q)

    print(f"[ROUTER] Query='{q}'  → Mode={mode}")

    if mode == "structured":
        result = postgres_structured_search(q)
        return {
            "mode": "structured",
            "result": result
        }

    elif mode == "semantic":
        result = vector_search(q)
        return {
            "mode": "semantic",
            "result": result
        }

    else:
        result = hybrid_search(q)
        return {
            "mode": "hybrid",
            "result": result
        }
