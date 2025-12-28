from typing import Dict, List, Tuple, Optional
import psycopg2
from psycopg2.extras import RealDictCursor


class SQLQueryBuilder:
    """
    Responsible ONLY for building deterministic SQL queries
    from structured filters.
    """

    BASE_SELECT = """
    SELECT
        project,
        version,
        mpu_name,
        rg_index,
        addr_start,
        addr_end,
        profile,
        raw_text
    FROM xml_chunks
    """

    def __init__(self, filters: Dict):
        self.filters = filters
        self.conditions: List[str] = []
        self.params: List = []

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

    def build(self) -> Tuple[str, List]:
        self._apply_project()
        self._apply_version()
        self._apply_mpu()

        where_clause = ""
        if self.conditions:
            where_clause = "WHERE " + " AND ".join(self.conditions)

        sql = f"""
        {self.BASE_SELECT}
        {where_clause}
        ORDER BY rg_index ASC
        """

        return sql.strip(), self.params


class SQLExecutor:
    """
    Responsible ONLY for executing SQL and returning rows.
    """

    def __init__(self, connection):
        self.conn = connection

    def fetch_all(self, sql: str, params: Optional[List] = None) -> List[Dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()


class SQLRepository:
    """
    Facade class used by the application.
    Combines builder + executor.
    """

    def __init__(self, connection):
        self.executor = SQLExecutor(connection)

    def fetch_policies(self, filters: Dict) -> List[Dict]:
        builder = SQLQueryBuilder(filters)
        sql, params = builder.build()
        return self.executor.fetch_all(sql, params)