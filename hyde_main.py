import logging
import psycopg2

from rag.hyde_query import HydeQuery
from llm_query import QGenieEmbedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-main")

PG_DSN = "postgresql://raguser:ragpassword@postgres:5432/ragdb"


def vector_search(query_vector, limit=5):
    sql = """
    SELECT id, project, version, raw_text,
           embedding <=> %s AS distance
    FROM xml_chunks
    ORDER BY embedding <=> %s
    LIMIT %s;
    """
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (query_vector, query_vector, limit))
            return cur.fetchall()


def main():
    user_query = "Give me the policy for address 0xc2630000"

    logger.info("Running HyDE")
    hyde = HydeQuery()
    hyde_text = hyde.rewrite(user_query)

    logger.info("HyDE output: %s", hyde_text)

    embedder = QGenieEmbedding()
    query_vector = embedder.embed_one(hyde_text)

    logger.info("Embedding dimension = %d", len(query_vector))

    rows = vector_search(query_vector)

    logger.info("Top results:")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()