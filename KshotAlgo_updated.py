"""
K-SHOT RAG PIPELINE (PROJECT + RELEASE AWARE)

Responsibilities:
- K-shot XML → pattern learning
- QGenie LLM → query rewriting
- Embeddings → semantic search
- Weaviate → vector recall
- Postgres → source of truth
"""

from typing import List, Dict, Optional
import os
import xml.etree.ElementTree as ET
import psycopg2
from psycopg2.extras import RealDictCursor
import weaviate
from weaviate.classes.query import MetadataQuery

from qgenie.integrations.langchain.embeddings import QGenieEmbeddings
from qgenie.llm import QGenieLLM


# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

KSHOT_XML_PATH = "/data/kshot_examples.xml"
WEAVIATE_COLLECTION = "PolicyChunks"
TOP_K = 8

POSTGRES_DSN = {
    "host": "rag-postgres",
    "port": 5432,
    "dbname": "rag",
    "user": "rag",
    "password": "rag",
}

WEAVIATE_HOST = "rag-weaviate"
WEAVIATE_PORT = 8080


# -------------------------------------------------------------------
# CLIENTS
# -------------------------------------------------------------------

def get_pg():
    return psycopg2.connect(**POSTGRES_DSN)


def get_weaviate():
    return weaviate.connect_to_custom(
        http_host=WEAVIATE_HOST,
        http_port=WEAVIATE_PORT,
        http_secure=False,
        skip_init_checks=True,
    )


def get_embedder():
    return QGenieEmbeddings(model="text-embedding-3-large")


def get_llm():
    return QGenieLLM(model="qgenie-pro")


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------

def safe_text(el, default="Not specified"):
    return el.text.strip() if el is not None and el.text else default


# -------------------------------------------------------------------
# BUILD CHUNK TEXT (NORMALIZE PROJECT + RELEASE FOR KSHOT ONLY)
# -------------------------------------------------------------------

def build_chunk_text(
    prtn: ET.Element,
    mpu_name: str,
    project: str,
    release: str,
    normalize_project: bool,
    normalize_release: bool,
) -> str:
    project = "<PROJECT>" if normalize_project else project
    release = "<RELEASE>" if normalize_release else release

    index = prtn.attrib.get("index")
    profile = prtn.attrib.get("profile")
    start = prtn.attrib.get("start")
    end = prtn.attrib.get("end")

    flags = prtn.find("XPU_Rgn_FLAGS")
    static = flags.attrib.get("static", "unknown") if flags is not None else "unknown"

    rationale = safe_text(prtn.find("SecurityRationale"))
    poc = safe_text(prtn.find("SecurityRationalePoC"))

    return (
        f"Access policy region {index} for profile {profile}. "
        f"MPU: {mpu_name}. "
        f"Project: {project}. "
        f"Release: {release}. "
        f"Address range {start} to {end}. "
        f"Static policy: {static}. "
        f"Security rationale: {rationale}. "
        f"Proof of ownership: {poc}."
    )


# -------------------------------------------------------------------
# LOAD KSHOT EXAMPLES (XML → TEXT)
# -------------------------------------------------------------------

def load_kshot_examples(limit: int = 6) -> List[str]:
    tree = ET.parse(KSHOT_XML_PATH)
    root = tree.getroot()

    release = root.findtext("Version", "<RELEASE>")
    examples = []

    for mpu in root.findall(".//MPU"):
        mpu_name = mpu.attrib["name"]
        fqname = mpu.attrib.get("fqname", "<PROJECT>")
        project = fqname.split(".")[0]

        for prtn in mpu.findall("PRTn"):
            examples.append(
                build_chunk_text(
                    prtn,
                    mpu_name,
                    project,
                    release,
                    normalize_project=True,
                    normalize_release=True,
                )
            )
            if len(examples) >= limit:
                return examples

    return examples


# -------------------------------------------------------------------
# LLM QUERY REWRITER (K-SHOT)
# -------------------------------------------------------------------

def rewrite_query_with_llm(
    user_query: str,
    kshot_examples: List[str],
) -> str:
    llm = get_llm()

    prompt = [
        "You are an expert in MPU and access control policy analysis.",
        "Below are example policy patterns:\n",
    ]

    for i, ex in enumerate(kshot_examples, 1):
        prompt.append(f"Example {i}:\n{ex}\n")

    prompt.append("User question:")
    prompt.append(user_query)

    prompt.append(
        "\nRewrite the user question into a precise semantic query "
        "that would retrieve the most relevant MPU policy regions. "
        "Do not invent facts. Do not mention specific project names "
        "or releases unless explicitly required. Return only the rewritten query."
    )

    return llm.chat("\n".join(prompt)).strip()


# -------------------------------------------------------------------
# VECTOR SEARCH
# -------------------------------------------------------------------

def vector_search(query_vector: List[float]) -> List[Dict]:
    client = get_weaviate()
    col = client.collections.get(WEAVIATE_COLLECTION)

    res = col.query.near_vector(
        vector=query_vector,
        limit=TOP_K,
        return_metadata=MetadataQuery(distance=True),
    )

    hits = [
        {"vector_id": str(o.uuid), "distance": o.metadata.distance}
        for o in res.objects
    ]

    client.close()
    return hits


# -------------------------------------------------------------------
# SQL FETCH WITH OPTIONAL PROJECT / RELEASE FILTERS
# -------------------------------------------------------------------

def fetch_chunks(
    pg,
    vector_ids: List[str],
    project: Optional[str],
    version: Optional[str],
):
    clauses = ["vector_id = ANY(%s)", "is_active = TRUE"]
    params = [vector_ids]

    if project:
        clauses.append("project = %s")
        params.append(project)

    if version:
        clauses.append("version = %s")
        params.append(version)

    sql = f"""
    SELECT *
    FROM policy_chunks
    WHERE {" AND ".join(clauses)}
    """

    with pg.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# -------------------------------------------------------------------
# ENTRYPOINT
# -------------------------------------------------------------------

def run_kshot_rag(
    user_query: str,
    project: Optional[str] = None,
    version: Optional[str] = None,
):
    kshots = load_kshot_examples()
    rewritten = rewrite_query_with_llm(user_query, kshots)

    embedder = get_embedder()
    query_vector = embedder.embed_query(rewritten)

    hits = vector_search(query_vector)

    pg = get_pg()
    chunks = fetch_chunks(
        pg,
        [h["vector_id"] for h in hits],
        project,
        version,
    )
    pg.close()

    score_map = {h["vector_id"]: 1 / (1 + h["distance"]) for h in hits}

    return [
        {**c, "semantic_score": score_map.get(c["vector_id"], 0.0)}
        for c in chunks
    ]


if __name__ == "__main__":
    results = run_kshot_rag(
        user_query="Why is IPA MPU static?",
        project="KAANAPALI",
        version=None,
    )

    for r in results:
        print("=" * 80)
        print(f"Score: {r['semantic_score']:.3f}")
        print(r["chunk_text"])