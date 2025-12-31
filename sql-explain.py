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

POINT_EXPLAIN_SELECT = """
SELECT
    *,
    (addr_end - addr_start) AS region_size,
    (%s BETWEEN addr_start AND addr_end) AS covers_address
FROM (
    {base}
) t
"""

RANGE_EXPLAIN_SELECT = """
SELECT
    *,
    GREATEST(addr_start, %s) AS overlap_start,
    LEAST(addr_end, %s) AS overlap_end,
    LEAST(addr_end, %s) - GREATEST(addr_start, %s) AS overlap_size
FROM (
    {base}
) t
"""


class SQLQueryBuilder:
    def __init__(self):
        self.filters = {}
        self.params = []

    # ---------- filter helpers ----------

    def with_project(self, project: str):
        self.filters["project"] = project.lower()
        return self

    def with_version(self, version: str | None):
        if version:
            self.filters["version"] = version
        else:
            self.filters["is_latest"] = True
        return self

    def with_mpu(self, mpu_name: str | None):
        if mpu_name:
            self.filters["mpu_name"] = mpu_name
        return self

    def with_address(self, start: int | None, end: int | None):
        if start is not None:
            self.filters["addr_start"] = start
        if end is not None:
            self.filters["addr_end"] = end
        return self

    # ---------- build ----------

    def build(self) -> tuple[str, list]:
        base_sql, base_params = self._build_base_where()

        addr_start = self.filters.get("addr_start")
        addr_end = self.filters.get("addr_end")

        # ---------- POINT ADDRESS QUERY ----------
        if addr_start is not None and addr_end is None:
            sql = POINT_EXPLAIN_SELECT.format(base=base_sql)
            params = [addr_start] + base_params
            sql += """
            WHERE addr_start <= %s
              AND addr_end   >= %s
            ORDER BY region_size ASC, rg_index DESC
            LIMIT 1
            """
            params += [addr_start, addr_start]
            return sql, params

        # ---------- RANGE ADDRESS QUERY ----------
        if addr_start is not None and addr_end is not None:
            sql = RANGE_EXPLAIN_SELECT.format(base=base_sql)
            params = [addr_start, addr_end, addr_end, addr_start] + base_params
            sql += """
            WHERE addr_start <= %s
              AND addr_end   >= %s
            ORDER BY overlap_size DESC, rg_index DESC
            """
            params += [addr_end, addr_start]
            return sql, params

        # ---------- NON-ADDRESS QUERY ----------
        return base_sql, base_params

    # ---------- base WHERE builder ----------

    def _build_base_where(self):
        clauses = []
        params = []

        if "project" in self.filters:
            clauses.append("project = %s")
            params.append(self.filters["project"])

        if "version" in self.filters:
            clauses.append("version = %s")
            params.append(self.filters["version"])
        elif self.filters.get("is_latest"):
            clauses.append("is_latest = true")

        if "mpu_name" in self.filters:
            clauses.append("mpu_name = %s")
            params.append(self.filters["mpu_name"])

        sql = BASE_SELECT
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        return sql, params