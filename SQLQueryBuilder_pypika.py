from pypika import Query, Table, functions as fn
from queryfacts import QueryFacts


XML = Table("xml_chunks")
PROJECTS = Table("project_versions")


class SQLQueryBuilder:
    """
    Builds SQL from QueryFacts.
    No routing, no intent detection, no DB calls.
    """

    def build(self, facts: QueryFacts) -> str:
        if facts.intent == "CATALOG":
            return self._build_catalog(facts)

        if facts.intent in ("LOOKUP", "POLICY", "REGION"):
            return self._build_xml_lookup(facts)

        raise ValueError(f"Unsupported intent: {facts.intent}")

    # -------------------------
    # CATALOG
    # -------------------------
    def _build_catalog(self, facts: QueryFacts) -> str:
        q = Query.from_(PROJECTS)

        if facts.operation == "COUNT":
            q = q.select(fn.Count("*"))
        else:
            q = q.select(
                PROJECTS.project,
                PROJECTS.version
            )

        if facts.project:
            q = q.where(PROJECTS.project == facts.project)

        if facts.version:
            q = q.where(PROJECTS.version == facts.version)

        return q.get_sql()

    # -------------------------
    # XML / POLICY / REGION
    # -------------------------
    def _build_xml_lookup(self, facts: QueryFacts) -> str:
        q = Query.from_(XML)

        if facts.operation == "COUNT":
            q = q.select(fn.Count("*"))
        else:
            q = q.select("*")

        if facts.project:
            q = q.where(XML.project == facts.project)

        if facts.version:
            q = q.where(XML.version == facts.version)

        if facts.mpu_name:
            q = q.where(XML.mpu_name == facts.mpu_name)

        if facts.profile:
            q = q.where(XML.profile == facts.profile)

        if facts.addr_start is not None:
            q = q.where(XML.addr_start >= facts.addr_start)

        if facts.addr_end is not None:
            q = q.where(XML.addr_end <= facts.addr_end)

        return q.get_sql()