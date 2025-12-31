class SQLQueryBuilder:
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

    EXPLAIN_SELECT = """
    ,
    (addr_end - addr_start) AS region_size,
    (%s BETWEEN addr_start AND addr_end) AS covers_address
    """

    def __init__(self, filters: dict, connection):
        self.filters = filters
        self.conn = connection
        self.conditions: list[str] = []
        self.params: list = []

    # -------------------------
    # Filter application
    # -------------------------

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

    def _apply_profile(self):
        if self.filters.get("profile"):
            self.conditions.append("profile = %s")
            self.params.append(self.filters["profile"])

    def _apply_address_overlap(self):
        start = self.filters.get("addr_start")
        end = self.filters.get("addr_end")

        if start is None:
            return False  # not an address query

        if end is None:
            end = start  # point query collapses to range

        self.conditions.append("addr_start <= %s")
        self.params.append(end)

        self.conditions.append("addr_end >= %s")
        self.params.append(start)

        return True  # address-based query

    # -------------------------
    # Build
    # -------------------------

    def build(self) -> tuple[str, list]:
        self._apply_project()
        self._apply_version()
        self._apply_mpu()
        self._apply_profile()

        is_address_query = self._apply_address_overlap()

        select = self.BASE_SELECT

        if is_address_query:
            select = select.replace(
                "FROM xml_chunks",
                self.EXPLAIN_SELECT + "\nFROM xml_chunks",
            )
            # explainability param (point address)
            self.params.insert(0, self.filters["addr_start"])

        where_clause = (
            "WHERE " + " AND ".join(self.conditions)
            if self.conditions
            else ""
        )

        order_clause = ""
        limit_clause = ""

        if is_address_query:
            order_clause = "ORDER BY (addr_end - addr_start) ASC, rg_index DESC"
            limit_clause = "LIMIT 1"

        sql = f"""
        {select}
        {where_clause}
        {order_clause}
        {limit_clause}
        """

        return sql.strip(), self.params