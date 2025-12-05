"""
Unified RAG API with Internal Query Router
------------------------------------------

Public Endpoints:
- POST /query   -> All user-facing retrieval (semantic + address + exact)
- POST /compare -> Deterministic MPU diff (Postgres only)

Run:
  uvicorn rag_api:app --host 0.0.0.0 --port 9000
"""

from typing import List, Optional, Dict, Any, Tuple
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import psycopg2
import weaviate


# -----------------------------
# CONFIG
# -----------------------------

WEAVIATE_URL = "http://localhost:8080"
WEAVIATE_CLASS = "AccessControlPolicy"

PG_HOST = "localhost"
PG_DB = "ragdb"
PG_USER = "raguser"
PG_PASSWORD = "ragpass"


# -----------------------------
# CONNECTIONS
# -----------------------------

pg = psycopg2.connect(
    host=PG_HOST,
    dbname=PG_DB,
    user=PG_USER,
    password=PG_PASSWORD,
)
pg.autocommit = True

wv = weaviate.Client(WEAVIATE_URL)

app = FastAPI(title="Unified Security Policy RAG API")


# -----------------------------
# REQUEST MODELS
# -----------------------------

class AddressRange(BaseModel):
    start_hex: str
    end_hex: str


class QueryRequest(BaseModel):
    project: str

    mode: Optional[str] = "AUTO"   # AUTO | SEMANTIC | ADDRESS | EXACT

    semantic_query: Optional[str] = None
    address_range: Optional[AddressRange] = None

    mpu_name: Optional[str] = None
    profile: Optional[str] = None

    policy_version: Optional[str] = None  # null => active
    limit: int = 5


class CompareRequest(BaseModel):
    project_a: str
    project_b: str
    mpu_name: str


# -----------------------------
# HELPERS
# -----------------------------

def pg_fetch_rows(query: str, params: tuple) -> List[Dict[str, Any]]:
    cur = pg.cursor()
    cur.execute(query, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def build_chunk_text(row: Dict[str, Any]) -> str:
    rdom = ", ".join(row["rdomains"] or [])
    wdom = ", ".join(row["wdomains"] or [])

    return f"""MPU: {row['mpu_name']}
Project: {row['project']}
Profile: {row.get('profile')}
RG Index: {row['rg_index']}
Start: {row.get('start_hex')}
End: {row.get('end_hex')}
Read Domains: {rdom or '<none>'}
Write Domains: {wdom or '<none>'}
Static: {row.get('static')}
Confirmed: {row.get('confirmed')}

Policy ID: {row.get('policy_id')}
""".strip()


# -----------------------------
# ROUTERS
# -----------------------------

def route_by_address(req: QueryRequest):
    start = int(req.address_range.start_hex, 16)
    end   = int(req.address_range.end_hex, 16)

    version_clause = (
        "policy_version = %s" if req.policy_version
        else "is_active = true"
    )

    sql = f"""
    SELECT *
    FROM policy_chunks
    WHERE project = %s
      AND {version_clause}
      AND NOT (end_dec < %s OR start_dec > %s)
    ORDER BY mpu_name, rg_index;
    """

    params = (
        (req.project, req.policy_version, start, end)
        if req.policy_version
        else (req.project, start, end)
    )

    rows = pg_fetch_rows(sql, params)

    return {
        "mode": "ADDRESS",
        "hit_count": len(rows),
        "results": [
            {
                "chunk_id": r["chunk_id"],
                "metadata": r,
                "chunk_text": build_chunk_text(r),
            }
            for r in rows
        ],
    }


def route_semantic(req: QueryRequest):
    # Build Weaviate filters
    filters = [
        {"path": ["project"], "operator": "Equal", "valueString": req.project}
    ]

    if req.mpu_name:
        filters.append(
            {"path": ["mpu_name"], "operator": "Equal", "valueString": req.mpu_name}
        )

    if req.profile:
        filters.append(
            {"path": ["profile"], "operator": "Equal", "valueString": req.profile}
        )

    where_clause = (
        f"where: {{ operator: And, operands: {filters} }}"
        if len(filters) > 1
        else f"where: {filters[0]}"
    )

    gql = f"""
    {{
      Get {{
        {WEAVIATE_CLASS}(
          nearText: {{ concepts: ["{req.semantic_query}"] }}
          {where_clause}
          limit: {req.limit}
        ) {{
          _additional {{ id distance }}
        }}
      }}
    }}
    """

    res = wv.query.raw(gql)
    hits = res["data"]["Get"][WEAVIATE_CLASS]

    if not hits:
        return {"mode": "SEMANTIC", "hit_count": 0, "results": []}

    ids = [h["_additional"]["id"] for h in hits]

    version_clause = (
        "policy_version = %s" if req.policy_version
        else "is_active = true"
    )

    sql = f"""
    SELECT *
    FROM policy_chunks
    WHERE weaviate_object_id = ANY(%s)
      AND {version_clause};
    """

    rows = pg_fetch_rows(
        sql,
        (ids, req.policy_version) if req.policy_version else (ids,),
    )

    row_map = {str(r["chunk_id"]): r for r in rows}

    results = []
    for h in hits:
        wid = h["_additional"]["id"]
        row = row_map.get(wid)
        if not row:
            continue

        results.append(
            {
                "chunk_id": wid,
                "similarity": 1.0 - h["_additional"]["distance"],
                "metadata": row,
                "chunk_text": build_chunk_text(row),
            }
        )

    return {
        "mode": "SEMANTIC",
        "hit_count": len(results),
        "results": results,
    }


def route_exact(req: QueryRequest):
    version_clause = (
        "policy_version = %s" if req.policy_version
        else "is_active = true"
    )

    sql = f"""
    SELECT *
    FROM policy_chunks
    WHERE project = %s
      AND {version_clause}
      AND (%s IS NULL OR mpu_name = %s)
      AND (%s IS NULL OR profile  = %s)
    ORDER BY mpu_name, rg_index;
    """

    params = (
        (req.project, req.policy_version, req.mpu_name, req.mpu_name, req.profile, req.profile)
        if req.policy_version
        else (req.project, req.mpu_name, req.mpu_name, req.profile, req.profile)
    )

    rows = pg_fetch_rows(sql, params)

    return {
        "mode": "EXACT",
        "hit_count": len(rows),
        "results": [
            {
                "chunk_id": r["chunk_id"],
                "metadata": r,
                "chunk_text": build_chunk_text(r),
            }
            for r in rows
        ],
    }


# -----------------------------
# UNIFIED /query ENDPOINT
# -----------------------------

@app.post("/query")
def unified_query(req: QueryRequest):
    """
    AUTO routing:
    - If address_range present  -> ADDRESS
    - Else if semantic_query    -> SEMANTIC
    - Else                      -> EXACT
    """

    if req.mode == "ADDRESS" or (req.mode == "AUTO" and req.address_range):
        return route_by_address(req)

    if req.mode == "SEMANTIC" or (req.mode == "AUTO" and req.semantic_query):
        return route_semantic(req)

    if req.mode == "EXACT" or req.mode == "AUTO":
        return route_exact(req)

    raise HTTPException(status_code=400, detail="Invalid query mode")


# -----------------------------
# /compare (UNCHANGED)
# -----------------------------

@app.post("/compare")
def compare_projects(req: CompareRequest):
    sql = """
    SELECT project, mpu_name, rg_index, profile,
           start_dec, end_dec, rdomains, wdomains,
           static, confirmed
    FROM policy_chunks
    WHERE project = %s
      AND mpu_name = %s
      AND is_active = true
    ORDER BY rg_index, profile;
    """

    a_rows = pg_fetch_rows(sql, (req.project_a, req.mpu_name))
    b_rows = pg_fetch_rows(sql, (req.project_b, req.mpu_name))

    def idx(rows):
        return {(r["rg_index"], r["profile"]): r for r in rows}

    A, B = idx(a_rows), idx(b_rows)

    only_a, only_b, changed = [], [], []

    keys = set(A) | set(B)
    for k in keys:
        if k in A and k not in B:
            only_a.append(A[k])
        elif k in B and k not in A:
            only_b.append(B[k])
        else:
            diffs = {}
            for f in ["start_dec", "end_dec", "rdomains", "wdomains", "static", "confirmed"]:
                if A[k][f] != B[k][f]:
                    diffs[f] = {req.project_a: A[k][f], req.project_b: B[k][f]}
            if diffs:
                changed.append({"rg_index": k[0], "profile": k[1], "diffs": diffs})

    return {
        "project_a": req.project_a,
        "project_b": req.project_b,
        "mpu_name": req.mpu_name,
        "only_in_a": only_a,
        "only_in_b": only_b,
        "changed": changed,
    }