from typing import Dict, List, Optional
from psycopg2.extras import RealDictCursor
import numpy as np


class QueryEmbedder:
    """
    Responsible ONLY for converting text → embedding vector.
    Plug in your in-house embedding model here.
    """

    def __init__(self, embed_fn):
        """
        embed_fn: callable(text: str) -> List[float]
        """
        self.embed_fn = embed_fn

    def embed(self, text: str) -> List[float]:
        return self.embed_fn(text)


class VectorQueryBuilder:
    """
    Builds vector SQL query with optional structured filters.
    """

    BASE_QUERY = """
    SELECT
        project,
        version,
        mpu_name,
        rg_index,
        addr_start,
        addr_end,
        profile,
        raw_text,
        1 - (embedding <=> %s) AS similarity
    FROM xml_chunks
    """

    def __init__(self, filters: Dict):
        self.filters = filters
        self.conditions = []
        self.params = []

    def _apply_project(self):
        if self.filters.get("project"):
            self.conditions.append("project = %s")
            self.params.append(self.filters["project"])

    def _apply_version(self):
        if self.filters.get("version"):
            self.conditions.append("version = %s")
            self.params.append(self.filters["version"])

    def _apply_mpu(self):
        if self.filters.get("mpu_name"):
            self.conditions.append("mpu_name = %s")
            self.params.append(self.filters["mpu_name"])

    def build(self, embedding: List[float], top_k: int):
        self._apply_project()
        self._apply_version()
        self._apply_mpu()

        where_clause = ""
        if self.conditions:
            where_clause = "WHERE " + " AND ".join(self.conditions)

        sql = f"""
        {self.BASE_QUERY}
        {where_clause}
        ORDER BY embedding <=> %s
        LIMIT {top_k}
        """

        # embedding passed twice: similarity + ordering
        params = [embedding] + self.params + [embedding]

        return sql.strip(), params


class VectorExecutor:
    """
    Executes vector similarity queries.
    """

    def __init__(self, connection):
        self.conn = connection

    def search(self, sql: str, params: List):
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


class VectorRepository:
    """
    Facade used by RAG layer.
    """

    def __init__(self, connection, embedder: QueryEmbedder):
        self.conn = connection
        self.embedder = embedder
        self.executor = VectorExecutor(connection)

    def semantic_search(
        self,
        query_text: str,
        filters: Dict,
        top_k: int = 10
    ) -> List[Dict]:
        embedding = self.embedder.embed(query_text)

        builder = VectorQueryBuilder(filters)
        sql, params = builder.build(embedding, top_k)

        return self.executor.search(sql, params)