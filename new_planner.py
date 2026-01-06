# planner.py
from typing import Dict, List


class PlannerError(Exception):
    pass


class QueryPlanner:
    """
    Deterministic planner.
    Input: QueryFacts (from Instructor)
    Output: executor name (string)
    """

    def __init__(self):
        # (intent, operation, entity) -> executor
        self.ROUTES: Dict[tuple, str] = {
            # POLICY domain
            ("POLICY", "LIST", "REGION"): "policy_region_list",
            ("POLICY", "LIST", "POLICY"): "policy_list",
            ("POLICY", "COUNT", "REGION"): "policy_region_count",
            ("POLICY", "COUNT", "POLICY"): "policy_count",

            # CATALOG domain
            ("CATALOG", "LIST", "PROJECT"): "project_list",
            ("CATALOG", "COUNT", "PROJECT"): "project_count",
            ("CATALOG", "LIST", "VERSION"): "project_version_list",
        }

    def plan(self, facts) -> str:
        """
        Decide executor from QueryFacts.
        """

        intent = facts.intent
        operation = facts.operation
        entities: List[str] = facts.entity or []

        if not intent or not operation:
            raise PlannerError(
                f"Missing intent/operation in QueryFacts: intent={intent}, operation={operation}"
            )

        # Try routing using each entity
        matched = []
        for entity in entities:
            key = (intent, operation, entity)
            if key in self.ROUTES:
                matched.append(self.ROUTES[key])

        if len(matched) == 1:
            return matched[0]

        if len(matched) > 1:
            raise PlannerError(
                f"Ambiguous planner route for intent={intent}, "
                f"operation={operation}, entities={entities}. "
                f"Matched executors={matched}"
            )

        raise PlannerError(
            f"No planner route for intent={intent}, "
            f"operation={operation}, entities={entities}"
        )