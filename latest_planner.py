from typing import List, Dict, Optional
from dataclasses import dataclass


# -------------------------------------------------
# QueryFacts contract (import if already defined)
# -------------------------------------------------

@dataclass
class QueryFacts:
    intent: Optional[str]               # ADDRESS_LOOKUP | POLICY_LOOKUP | PROFILE_LOOKUP
    project: Optional[str]
    version: Optional[str]
    mpu_name: Optional[str]
    addr_start: Optional[int]
    addr_end: Optional[int]
    profile: Optional[str]
    domains: Optional[list]
    wdomains: Optional[list]


# -------------------------------------------------
# Planner
# -------------------------------------------------

class Planner:
    """
    Converts QueryFacts into an executable plan.
    Planner is declarative — it decides WHAT to do, not HOW.
    """

    def plan(self, facts: QueryFacts) -> List[Dict]:
        if not facts.intent:
            return [self._clarify("Missing intent")]

        intent = facts.intent.upper()

        if intent == "ADDRESS_LOOKUP":
            return self._plan_address_lookup(facts)

        if intent == "POLICY_LOOKUP":
            return self._plan_policy_lookup(facts)

        if intent == "PROFILE_LOOKUP":
            return self._plan_profile_lookup(facts)

        return [self._clarify(f"Unsupported intent: {facts.intent}")]

    # -------------------------------------------------
    # ADDRESS LOOKUP (SQL → Vector fallback)
    # -------------------------------------------------

    def _plan_address_lookup(self, facts: QueryFacts) -> List[Dict]:
        """
        Address based MPU lookup:
        1. Exact SQL lookup (project/mpu/version)
        2. Vector fallback if SQL is empty
        """

        plans: List[Dict] = []

        plans.append({
            "action": "SQL_SEARCH",
            "params": {
                "project": facts.project,
                "version": facts.version,
                "mpu_name": facts.mpu_name,
                "addr_start": facts.addr_start,
                "addr_end": facts.addr_end,
                "profile": facts.profile,
            },
            "depends_on": []
        })

        plans.append({
            "action": "VECTOR_SEARCH",
            "params": {
                "semantic_query": self._semantic_hint(facts),
                "project": facts.project,
                "version": facts.version,
                "mpu_name": facts.mpu_name,
                "top_k": 10
            },
            "depends_on": [0]
        })

        return plans

    # -------------------------------------------------
    # POLICY LOOKUP (Vector-first)
    # -------------------------------------------------

    def _plan_policy_lookup(self, facts: QueryFacts) -> List[Dict]:
        return [{
            "action": "VECTOR_SEARCH",
            "params": {
                "semantic_query": self._semantic_hint(facts),
                "project": facts.project,
                "version": facts.version,
                "top_k": 20
            },
            "depends_on": []
        }]

    # -------------------------------------------------
    # PROFILE LOOKUP (SQL-only)
    # -------------------------------------------------

    def _plan_profile_lookup(self, facts: QueryFacts) -> List[Dict]:
        return [{
            "action": "SQL_SEARCH",
            "params": {
                "project": facts.project,
                "version": facts.version,
                "profile": facts.profile,
            },
            "depends_on": []
        }]

    # -------------------------------------------------
    # Helpers
    # -------------------------------------------------

    def _semantic_hint(self, facts: QueryFacts) -> str:
        """
        Build a safe semantic hint for vector search.
        This must never invent data.
        """
        parts = []

        if facts.project:
            parts.append(f"project {facts.project}")

        if facts.mpu_name:
            parts.append(f"MPU {facts.mpu_name}")

        if facts.profile:
            parts.append(f"profile {facts.profile}")

        if facts.intent:
            parts.append(facts.intent.lower().replace("_", " "))

        if facts.domains:
            parts.append("domains " + ", ".join(facts.domains))

        if facts.wdomains:
            parts.append("write domains " + ", ".join(facts.wdomains))

        return " ".join(parts)

    def _clarify(self, reason: str) -> Dict:
        """
        Planner-level clarification request.
        Executor should route this directly to the user.
        """
        return {
            "action": "CLARIFY",
            "params": {
                "reason": reason
            },
            "depends_on": []
        }