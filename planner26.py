class Planner:
    """
    Enum-pure execution planner.
    """

    ROUTES = {
        # POLICY
        (Intent.POLICY, Operation.LOOKUP, Entity.ADDRESS): "policy_by_address",
        (Intent.POLICY, Operation.LOOKUP, Entity.REGION): "policy_by_region",
        (Intent.POLICY, Operation.LIST,   Entity.POLICY): "policy_list",
        (Intent.POLICY, Operation.COUNT,  Entity.POLICY): "policy_count",

        # CATALOG
        (Intent.CATALOG, Operation.LIST,  Entity.PROJECT): "project_list",
        (Intent.CATALOG, Operation.COUNT, Entity.PROJECT): "project_count",
        (Intent.CATALOG, Operation.LIST,  Entity.VERSION): "version_list",
        (Intent.CATALOG, Operation.COUNT, Entity.VERSION): "version_count",

        # COMPARE
        (Intent.COMPARE, Operation.COMPARE, Entity.POLICY): "policy_compare",
        (Intent.COMPARE, Operation.COMPARE, Entity.REGION): "region_compare",

        # VALIDATE
        (Intent.VALIDATE, Operation.VALIDATE, Entity.POLICY): "policy_validate",
        (Intent.VALIDATE, Operation.VALIDATE, Entity.REGION): "region_validate",
    }

    def plan(self, facts) -> PlanResult:
        """
        Decide executor from QueryFacts.
        Deterministic. Enum-safe. Debuggable.
        """

        intent = facts.intent
        operation = facts.operation
        entities = facts.entity or []

        # ---------------------------
        # Hard guards
        # ---------------------------
        if not isinstance(intent, Intent):
            raise PlannerError(f"Invalid intent type: {intent} ({type(intent)})")

        if not isinstance(operation, Operation):
            raise PlannerError(f"Invalid operation type: {operation} ({type(operation)})")

        if not entities:
            raise PlannerError(
                f"No entity provided for intent={intent}, operation={operation}"
            )

        for e in entities:
            if not isinstance(e, Entity):
                raise PlannerError(f"Invalid entity type: {e} ({type(e)})")

        # ---------------------------
        # Deterministic entity choice
        # ---------------------------
        entity = self._select_entity(intent, operation, entities)

        key = (intent, operation, entity)

        if key not in self.ROUTES:
            supported = [
                (i.name, o.name, e.name)
                for (i, o, e) in self.ROUTES.keys()
            ]
            raise PlannerError(
                f"No route for (intent={intent.name}, "
                f"operation={operation.name}, "
                f"entity={entity.name}).\n"
                f"Supported routes: {supported}"
            )

        return PlanResult(
            executor=self.ROUTES[key],
            intent=intent,
            operation=operation,
            entity=entity,
        )

    # ---------------------------
    # Entity selection rules
    # ---------------------------
    def _select_entity(
        self,
        intent: Intent,
        operation: Operation,
        entities: list[Entity],
    ) -> Entity:
        """
        Deterministic entity resolution.
        """

        # POLICY: ADDRESS beats REGION beats POLICY
        if intent == Intent.POLICY:
            for preferred in (
                Entity.ADDRESS,
                Entity.REGION,
                Entity.POLICY,
            ):
                if preferred in entities:
                    return preferred

        # CATALOG
        if intent == Intent.CATALOG:
            for preferred in (
                Entity.PROJECT,
                Entity.VERSION,
            ):
                if preferred in entities:
                    return preferred

        # COMPARE / VALIDATE → single entity only
        if intent in (Intent.COMPARE, Intent.VALIDATE):
            if len(entities) != 1:
                raise PlannerError(
                    f"{intent.name} requires exactly one entity, got {entities}"
                )
            return entities[0]

        # Fallback (safe default)
        return entities[0]