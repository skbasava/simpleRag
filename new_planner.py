from typing import Dict, Tuple, List
from dataclasses import dataclass

# import your QueryFacts model
from query_facts import QueryFacts


class PlannerError(Exception):
    """Raised when planner cannot deterministically route a query."""
    pass


@dataclass(frozen=True)
class PlanResult:
    executor: str
    intent: str
    operation: str
    entity: List[str]


class Planner:
    """
    Deterministic planner.
    Input  : QueryFacts (from Instructor)
    Output : Executor name (string)
    """

    def __init__(self) -> None:
        """
        Routing table:
        (intent, operation, entity) -> executor_name
        """

        self.ROUTES: Dict[Tuple[str, str, str], str] = {

            # -------- POLICY / REGION DATA (xml_chunks, policy tables) --------
            ("LOOKUP", "LOOKUP", "POLICY"): "policy_lookup",
            ("LOOKUP", "LOOKUP", "REGION"): "region_lookup",

            ("POLICY", "LIST", "POLICY"): "policy_list",
            ("POLICY", "LIST", "REGION"): "region_list",
            ("POLICY", "COUNT", "POLICY"): "policy_count",
            ("POLICY", "COUNT", "REGION"): "region_count",

            # -------- PROJECT / VERSION CATALOG (project_version tables) --------
            ("CATALOG", "LIST", "PROJECT"): "project_list",
            ("CATALOG", "COUNT", "PROJECT"): "project_count",

            ("CATALOG", "LIST", "VERSION"): "project_version_list",
            ("CATALOG", "COUNT", "VERSION"): "project_version_count",

            # -------- COMPARISON --------
            ("COMPARE", "COMPARE", "POLICY"): "policy_compare",
            ("COMPARE", "COMPARE", "REGION"): "region_compare",

            # -------- VALIDATION --------
            ("VALIDATE", "VALIDATE", "POLICY"): "policy_validate",
            ("VALIDATE", "VALIDATE", "REGION"): "region_validate",
        }

    def plan(self, facts: QueryFacts) -> PlanResult:
        """
        Decide executor from QueryFacts.

        This function MUST be:
        - deterministic
        - side-effect free
        - easy to debug
        """

        intent = facts.intent
        operation = facts.operation
        entities = facts.entity or []

        if not intent or not operation:
            raise PlannerError("Intent or operation missing in QueryFacts")

        if not entities:
            raise PlannerError(
                f"No entity provided for intent={intent}, operation={operation}"
            )

        matched: List[str] = []

        for entity in entities:
            key = (intent, operation, entity)
            if key in self.ROUTES:
                matched.append(self.ROUTES[key])

        if not matched:
            raise PlannerError(
                f"No route for intent={intent}, operation={operation}, entities={entities}"
            )

        if len(matched) > 1:
            raise PlannerError(
                f"Ambiguous routing for intent={intent}, operation={operation}, "
                f"entities={entities}. Matched executors={matched}"
            )

        return PlanResult(
            executor=matched[0],
            intent=intent,
            operation=operation,
            entity=entities,
        )