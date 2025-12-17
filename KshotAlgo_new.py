"""
K-SHOT RAG PIPELINE (XML-BASED EXAMPLES)

- K-shot examples are loaded from XML files
- Same build_chunk_text() logic as ingestion
- Weaviate = semantic recall
- Postgres = source of truth
"""

from typing import List, Dict
import os
import xml.etree.ElementTree as ET
import psycopg2
from psycopg2.extras import RealDictCursor
import weaviate
from weaviate.classes.query import MetadataQuery
from qgenie.integrations.langchain.embeddings import QGenieEmbeddings


# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

WEAVIATE_COLLECTION = "PolicyChunks"
K = 5

KSHOT_XML_DIR = "/data/kshot_examples_xml"   # 👈 XML now
WEAVIATE_HOST = "rag-weaviate"
WEAVIATE_PORT = 8080

POSTGRES_DSN = {
    "host": "rag-postgres",
    "port": 5432,
    "dbname": "rag",
    "user": "rag",
    "password": "rag",
}


# -------------------------------------------------------------------
# CLIENTS
# -------------------------------------------------------------------

def get_weaviate_client():
    return weaviate.connect_to_custom(
        http_host=WEAVIATE_HOST,
        http_port=WEAVIATE_PORT,
        http_secure=False,
        grpc_host=WEAVIATE_HOST,
        grpc_port=50051,
        grpc_secure=False,
        skip_init_checks=True,
    )


def get_pg_conn():
    return psycopg2.connect(**POSTGRES_DSN)


def get_embedder():
    return QGenieEmbeddings(
        model="text-embedding-3-large"
    )


# -------------------------------------------------------------------
# XML → CHUNK_TEXT (same logic as ingestion)
# -------------------------------------------------------------------

def safe_text(el, default="Not specified"):
    if el is None or el.text is None:
        return default
    return el.text.strip()


def build_chunk_text(prtn: ET.Element) -> str:
    index = prtn.attrib.get("index", "unknown")
    profile = prtn.attrib.get("profile", "unknown")
    start = prtn.attrib.get("start", "unknown")
    end = prtn.attrib.get("end", "unknown")

    rdomains = prtn.attrib.get("rdomains") or "none"
    wdomains = prtn.attrib.get("wdomains") or "none"

    rationale = safe_text(prtn.find("SecurityRationale"))
    poc = safe_text(prtn.find("SecurityRationalePoC"))

    flags_el = prtn.find("XPU_Rgn_FLAGS")
    enabled = flags_el.attrib.get("enabled", "unknown") if flags_el is not None else "unknown"
    static = flags_el.attrib.get("static", "unknown") if flags_el is not None else "unknown"

    return (
        f"Access policy region {index} for profile {profile}. "
        f"Address range {start} to {end}. "
        f"Static policy: {static}. "
        f"Read domains: {rdomains}. "
        f"Write domains: {wdomains}. "
        f"Security rationale: {rationale}. "
        f"Proof of ownership: {poc}."
    )


# -------------------------------------------------------------------
# LOAD K-SHOT EXAMPLES FROM XML
# -------------------------------------------------------------------

def load_kshot_examples_from_xml(max_examples: int = 5) -> List[str]:
    """
    Parse XML files and extract chunk_text from <PRTn>
    """
    examples = []

    for fname in sorted(os.listdir(KSHOT_XML_DIR)):
        if not fname.endswith(".xml"):
            continue

        path = os.path.join(KSHOT_XML_DIR, fname)
        tree = ET.parse(path)
        root = tree.getroot()

        for prtn in root.findall(".//PRTn"):
            examples.append(build_chunk_text(prtn))
            if len(examples) >= max_examples:
                return examples

    return examples


# -------------------------------------------------------------------
# K-SHOT QUERY BUILDER
# -------------------------------------------------------------------

def build_kshot_query(user_query: str, examples: List[str]) -> str:
    parts = [
        "You are searching access control policy knowledge.",
        "Below are example policy regions:\n",
    ]

    for i, ex in enumerate(examples, 1):
        parts.append(f"Example {i}:\n{ex}\n")

    parts.append("User query:")
    parts.append(user_query)
    parts.append("\nFind the most relevant policy regions.")

    return "\n".join(parts)


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

    hits = [
        {
            "vector_id": str(obj.uuid),
            "distance": obj.metadata.distance
        }
        for obj in res.objects
    ]

    client.close()
    return hits


# -------------------------------------------------------------------
# POSTGRES FETCH
# -------------------------------------------------------------------

def fetch_chunks_by_vector_ids(pg_conn, vector_ids: List[str]) -> List[Dict]:
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
        vector_id
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

def merge_scores(weaviate_hits, pg_chunks):
    score_map = {
        h["vector_id"]: 1 / (1 + h["distance"])
        for h in weaviate_hits
    }
    order_map = {h["vector_id"]: i for i, h in enumerate(weaviate_hits)}

    enriched = []
    for c in pg_chunks:
        enriched.append({
            **c,
            "semantic_score": score_map.get(c["vector_id"], 0.0),
            "rank": order_map.get(c["vector_id"], 999),
        })

    enriched.sort(key=lambda x: x["rank"])
    return enriched


# -------------------------------------------------------------------
# MAIN ENTRY
# -------------------------------------------------------------------

def run_kshot_rag(user_query: str):
    examples = load_kshot_examples_from_xml()
    query_text = build_kshot_query(user_query, examples)

    embedder = get_embedder()
    query_vector = embedder.embed_query(query_text)

    hits = search_weaviate(query_vector, K)

    pg = get_pg_conn()
    chunks = fetch_chunks_by_vector_ids(pg, [h["vector_id"] for h in hits])
    pg.close()

    return merge_scores(hits, chunks)


if __name__ == "__main__":
    query = "Why does ANOC_IPA_XPU have a static policy?"
    results = run_kshot_rag(query)

    for r in results:
        print("=" * 80)
        print(f"Score: {r['semantic_score']:.4f}")
        print(r["chunk_text"])