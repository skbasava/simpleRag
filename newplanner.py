INTENT_PLAN_TABLE = {
    # POLICY QUERIES → authoritative text
    Intent.POLICY: {
        "policy_by_address": OutputMode.TEXT,
        "policy_by_region":  OutputMode.TEXT,
    },

    # LIST / CATALOG QUERIES → structured rows
    Intent.CATALOG: {
        "project_list":  OutputMode.ROWS,
        "version_list":  OutputMode.ROWS,
    },

    Intent.LIST: {
        "policy_list":   OutputMode.ROWS,
        "project_list":  OutputMode.ROWS,
    },

    # EXPLAIN → text only
    Intent.EXPLAIN: {
        "policy_explain": OutputMode.TEXT,
    },

    # COUNT → rows (count is structured)
    Intent.COUNT: {
        "project_count": OutputMode.ROWS,
        "policy_count":  OutputMode.ROWS,
    }
}
class Planner:
    def plan(self, facts: QueryFacts) -> ExecutionPlan:
        if not facts.intent:
            raise ValueError("Planner: intent missing")

        intent_routes = INTENT_PLAN_TABLE.get(facts.intent)
        if not intent_routes:
            raise ValueError(f"No routes defined for intent {facts.intent}")

        # Decide executor (existing logic, simplified)
        executor_name = self._select_executor(facts, intent_routes)

        if executor_name not in intent_routes:
            raise ValueError(
                f"Executor {executor_name} not allowed for intent {facts.intent}"
            )

        expected_mode = intent_routes[executor_name]

        return ExecutionPlan(
            executor=executor_name,
            mode=expected_mode,
            params=self._build_executor_params(facts),
        )

    def _select_executor(self, facts: QueryFacts, routes: dict) -> str:
        # Minimal, explicit rules (no magic)
        if facts.intent == Intent.POLICY:
            if facts.address:
                return "policy_by_address"
            if facts.region:
                return "policy_by_region"

        if facts.intent == Intent.CATALOG:
            if facts.project:
                return "version_list"
            return "project_list"

        if facts.intent == Intent.COUNT:
            if facts.project:
                return "policy_count"
            return "project_count"

        raise ValueError(f"Unable to select executor for facts: {facts}")

    def _build_executor_params(self, facts: QueryFacts) -> dict:
        return facts.dict(exclude_none=True)



