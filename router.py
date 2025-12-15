# router.py
from rag.classifier import classify_query, QueryType
from ingest import get_cursor, weaviate_client


TOP_K = 8


class RAGRouter:
    def __init__(self):
        self.conn, self.cur = get_cursor()
        self.wv = weaviate_client()

    # ---------- Structured ----------
    def structured_search(self, filters: dict):
        sql = """
        SELECT chunk_text, project, mpu_name, profile, start_hex, end_hex
        FROM policy_chunks
        WHERE is_active = TRUE
          AND (%(project)s IS NULL OR project = %(project)s)
          AND (%(mpu)s IS NULL OR mpu_name = %(mpu)s)
          AND (%(profile)s IS NULL OR profile = %(profile)s)
        ORDER BY rg_index, chunk_index
        LIMIT 20
        """
        self.cur.execute(sql, filters)
        return [r[0] for r in self.cur.fetchall()]

    # ---------- Semantic ----------
    def semantic_search(self, query: str):
        res = (
            self.wv.query
            .get("PolicyChunk", ["chunk_text"])
            .with_near_text({"concepts": [query]})
            .with_limit(TOP_K)
            .do()
        )
        return [
            x["chunk_text"]
            for x in res["data"]["Get"]["PolicyChunk"]
        ]

    # ---------- Hybrid ----------
    def hybrid_search(self, query: str, filters: dict):
        structured = self.structured_search(filters)
        semantic = self.semantic_search(query)
        return structured[:4] + semantic[:4]

    # ---------- Entry ----------
    def route(self, query: str, filters: dict):
        qtype = classify_query(query)

        if qtype == QueryType.STRUCTURED:
            ctx = self.structured_search(filters)
        elif qtype == QueryType.SEMANTIC:
            ctx = self.semantic_search(query)
        else:
            ctx = self.hybrid_search(query, filters)

        return qtype, ctx
