import logging
from typing import List
import psycopg2

from llm_query import QGenieLLM, QGenieEmbedding

# --------------------------------------------------
# Config
# --------------------------------------------------
PG_DSN = "postgresql://raguser:ragpassword@postgres:5432/ragdb"
TOP_K = 5

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# Hyde + Embedding
# --------------------------------------------------
class HydeEncoder:
    """
    HyDE-lite:
    User Query -> LLM rewritten pseudo-answer -> embedding
    """

    SYSTEM_PROMPT = """
You rewrite user questions into a concise, factual description
that would likely appear in technical documentation.
Do NOT answer the question.
Do NOT add explanations.
Output only rewritten text.
"""

    def __init__(self):
        self.llm = QGenieLLM()
        self.embedder = QGenieEmbedding()

    def encode(self, user_query: str) -> List[float]:
        logger.info("Running HyDE rewrite")

        rewritten = self.llm.ask(
            prompt=user_query,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=128,
        )

        logger.info("HyDE output: %s", rewritten)

        vector = self.embedder.embed_one(rewritten)
        return vector


# --------------------------------------------------
# Vector Search
# --------------------------------------------------
class PgVectorSearcher:
    def __init__(self, dsn: str):
        self.conn = psycopg2.connect(dsn)

    def search(self, query_vector: List[float], limit: int = TOP_K):
        sql = """
        SELECT
            id,
            project,
            version,
            raw_text,
            1 - (embedding <=> %(vec)s) AS score
        FROM xml_chunks
        ORDER BY embedding <=> %(vec)s
        LIMIT %(limit)s
        """

        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                {
                    "vec": query_vector,
                    "limit": limit,
                },
            )
            return cur.fetchall()


# --------------------------------------------------
# Main RAG (HyDE + Vector Search only)
# --------------------------------------------------
class RagSearchApp:
    def __init__(self):
        self.encoder = HydeEncoder()
        self.searcher = PgVectorSearcher(PG_DSN)

    def run(self, user_query: str):
        logger.info("User query: %s", user_query)

        query_vector = self.encoder.encode(user_query)
        results = self.searcher.search(query_vector)

        return results


# --------------------------------------------------
# CLI entry
# --------------------------------------------------
if __name__ == "__main__":
    app = RagSearchApp()

    query = "Give me the policy for address 0xc2630000 in Kaanapalli"
    rows = app.run(query)

    print("\n=== VECTOR SEARCH RESULTS ===\n")
    for r in rows:
        print(f"[score={r[4]:.4f}] {r[1]} v{r[2]}")
        print(r[3])
        print("-" * 80)