"""
K-SHOT RAG PIPELINE FOR XML POLICY FILES

Flow:
1. Load K-shot examples from XML-derived text files
2. Build a strong query using examples + user query
3. Embed query
4. Search Weaviate (Top-K vectors)
5. Fetch payload from Postgres using vector_id
6. Merge semantic scores
"""

from typing import List, Dict
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import weaviate
from weaviate.classes.query import MetadataQuery
from qgenie.integrations.langchain.embeddings import QGenieEmbeddings


# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

WEAVIATE_URL = "http://rag-weaviate:8080"
WEAVIATE_COLLECTION = "PolicyChunks"

POSTGRES_DSN = {
    "host": "rag-postgres",
    "port": 5432,
    "dbname": "rag",
    "user": "rag",
    "password": "rag"
}

K = 5  # top-k vectors
KSHOT_DIR = "/data/kshot_examples"  # directory containing example txt files


# -------------------------------------------------------------------
# CLIENTS
# -------------------------------------------------------------------

def get_weaviate_client():
    return weaviate.connect_to_local(
        host="rag-weaviate",
        port=8080
    )


def get_pg_conn():
    return psycopg2.connect(**POSTGRES_DSN)


def get_embedder():
    return QGenieEmbeddings(
        model="text-embedding-3-large"
    )


# -------------------------------------------------------------------
# K-SHOT LOGIC
# -------------------------------------------------------------------

def load_kshot_examples() -> List[str]:
    """
    Read example chunks from files.
    Each file = one example chunk_text
    """
    examples = []
    for fname in sorted(os.listdir(KSHOT_DIR)):
        path = os.path.join(KSHOT_DIR, fname)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                examples.append(f.read().strip())
    return examples


def build_kshot_query(user_query: str, examples: List[str]) -> str:
    """
    Build a strong semantic query using examples
    """
    prompt = [
        "You are searching security access control policies.",
        "Below are examples of relevant policy chunks:",
        ""
    ]

    for i, ex in enumerate(examples, 1):
        prompt.append(f"Example {i}:\n{ex}\n")

    prompt.append("User question:")
    prompt.append(user_query)
    prompt.append("\nFind the most relevant policy chunks.")

    return "\n".join(prompt)


# -------------------------------------------------------------------
# WEAVIATE SEARCH
# -------------------------------------------------------------------

def search_weaviate(query_vector: List[float], top_k: int) -> List[Dict]:
    client = get_weaviate_client()
    col = client.collections.get(WEAVIATE_COLLECTION)

    res = col.query.near_vector(
        vector=query_vector,
        limit=top_k,
        return_metadata=MetadataQuery(distance=True)
    )

    hits = []
    for obj in res.objects:
        hits.append({
            "vector_id": str(obj.uuid),
            "distance": obj.metadata.distance
        })

    client.close()
    return hits


# -------------------------------------------------------------------
# POSTGRES FETCH
# -------------------------------------------------------------------

def fetch_chunks_by_vector_ids(pg_conn, vector_ids: List[str]) -> List[Dict]:
    if not vector_ids:
        return []

    sql = """
    SELECT
        id,
        project,
        version,
        mpu_name,
        rg_index,
        profile,
        start_hex,
        end_hex,
        chunk_index,
        chunk_text,
        identity_hash,
        content_hash,
        vector_id,
        created_at
    FROM policy_chunks
    WHERE vector_id = ANY(%s)
      AND is_active = TRUE
    """

    with pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (vector_ids,))
        return cur.fetchall()


# -------------------------------------------------------------------
# SCORE MERGE
# -------------------------------------------------------------------

def merge_scores(weaviate_hits: List[Dict], pg_chunks: List[Dict]) -> List[Dict]:
    """
    Convert distance → similarity score and merge
    """
    score_map = {
        h["vector_id"]: 1 / (1 + h["distance"])
        for h in weaviate_hits
    }

    order_map = {h["vector_id"]: i for i, h in enumerate(weaviate_hits)}

    enriched = []
    for chunk in pg_chunks:
        enriched.append({
            **chunk,
            "semantic_score": score_map.get(chunk["vector_id"], 0.0),
            "rank": order_map.get(chunk["vector_id"], 999)
        })

    enriched.sort(key=lambda c: c["rank"])
    return enriched


# -------------------------------------------------------------------
# MAIN ENTRY
# -------------------------------------------------------------------

def run_kshot_rag(user_query: str) -> List[Dict]:
    # 1. Load examples
    examples = load_kshot_examples()

    # 2. Build K-shot query
    final_query = build_kshot_query(user_query, examples)

    # 3. Embed query
    embedder = get_embedder()
    query_vector = embedder.embed_query(final_query)

    # 4. Weaviate search
    weaviate_hits = search_weaviate(query_vector, K)

    # 5. Fetch payloads from Postgres
    vector_ids = [h["vector_id"] for h in weaviate_hits]
    pg_conn = get_pg_conn()
    chunks = fetch_chunks_by_vector_ids(pg_conn, vector_ids)
    pg_conn.close()

    # 6. Merge scores
    return merge_scores(weaviate_hits, chunks)


# -------------------------------------------------------------------
# CLI / TEST
# -------------------------------------------------------------------

if __name__ == "__main__":
    query = "Which MPU regions use static policy and why?"
    results = run_kshot_rag(query)

    for r in results:
        print("=" * 80)
        print(f"Score: {r['semantic_score']:.4f}")
        print(f"MPU: {r['mpu_name']} | RG: {r['rg_index']} | Profile: {r['profile']}")
        print(r["chunk_text"])