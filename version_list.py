class VersionListExecutor(BaseExecutor):
    name = "version_list"
    requires_llm = False

    def execute(self, facts: QueryFacts) -> dict:
        if not facts.project:
            raise ExecutorError("project is required for version_list")

        rows = self.db.fetch_all(
            """
            SELECT version, is_latest
            FROM project_metadata
            WHERE project = %s
            ORDER BY ingested_at DESC
            """,
            (facts.project,)
        )

        return {
            "rows": rows,
            "project": facts.project,
        }

    def format_response(self, execution_result: dict) -> str:
        rows = execution_result["rows"]
        project = execution_result["project"]

        if not rows:
            return f"No versions found for project {project}."

        latest = next((r["version"] for r in rows if r["is_latest"]), None)

        if latest:
            return f"The latest version of project {project} is **{latest}**."

        # fallback
        versions = ", ".join(r["version"] for r in rows)
        return f"Project {project} has versions: {versions}"