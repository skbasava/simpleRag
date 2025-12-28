from typing import Dict, List, Tuple, Optional
import psycopg2
from psycopg2.extras import RealDictCursor


class LatestVersionResolver:
    """
    Resolves latest version for a project using project_versions table.
    """

    def __init__(self, connection):
        self.conn = connection

    def resolve(self, project: str) -> Optional[str]:
        sql = """
        SELECT version
        FROM project_versions
        WHERE project = %s AND is_latest = TRUE
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (project,))
            row = cur.fetchone()
            return row[0] if row else None


class SQLQueryBuilder:
    """
    Builds SQL deterministically from filters.
    Automatically resolves latest version if version is missing.
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

    def __init__(self, filters: Dict, connection):
        self.filters = filters
        self.conn = connection
        self.conditions: List[str] = []
        self.params: List = []

        self.version_resolver = LatestVersionResolver(connection)

    def _apply_project(self):
        if self.filters.get("project"):
            self.conditions.append("project = %s")
            self.params.append(self.filters["project"])

    def _apply_version(self):
        """
        If version not provided, auto-resolve latest for the project.
        """
        version = self.filters.get("version")

        if not version and self.filters.get("project"):
            version = self.version_resolver.resolve(self.filters["project"])

        if version:
            self.conditions.append("version = %s")
            self.params.append(version)

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
    Executes SQL and returns rows.
    """

    def __init__(self, connection):
        self.conn = connection

    def fetch_all(self, sql: str, params: Optional[List] = None) -> List[Dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()


class SQLRepository:
    """
    Facade used by application / RAG layer.
    """

    def __init__(self, connection):
        self.conn = connection
        self.executor = SQLExecutor(connection)

    def fetch_policies(self, filters: Dict) -> List[Dict]:
        builder = SQLQueryBuilder(filters, self.conn)
        sql, params = builder.build()
        return self.executor.fetch_all(sql, params)