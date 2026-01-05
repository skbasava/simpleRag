import re
from dataclasses import dataclass
from enum import Enum
from typing import List


class Route(str, Enum):
    TAG = "TAG"
    LLM = "LLM"


@dataclass
class IntentDecision:
    route: Route
    reason: str
    confidence: float


class ProductionIntentClassifier:

    ADDRESS_REGEX = re.compile(r"0x[0-9a-fA-F]+")
    RANGE_REGEX = re.compile(r"0x[0-9a-fA-F]+\s*[-–]\s*0x[0-9a-fA-F]+")
    REGION_REGEX = re.compile(r"\bregion\s+\d+\b")

    LOOKUP_VERBS = {
        "get", "give", "fetch", "show", "find",
        "list", "details", "access", "permissions"
    }

    EXPLAIN_VERBS = {
        "explain", "design", "architecture",
        "overview", "how", "why", "compare",
        "what is", "describe"
    }

    def classify(self, query: str) -> IntentDecision:
        q = query.lower()

        has_address = bool(
            self.ADDRESS_REGEX.search(q) or
            self.RANGE_REGEX.search(q) or
            self.REGION_REGEX.search(q)
        )

        has_lookup = any(v in q for v in self.LOOKUP_VERBS)
        has_explain = any(v in q for v in self.EXPLAIN_VERBS)

        # ---- Gate 2: Force LLM ----
        if has_explain:
            return IntentDecision(
                route=Route.LLM,
                reason="Conceptual / explanatory query",
                confidence=0.95
            )

        # ---- Gate 1: Strict TAG ----
        if has_address and has_lookup:
            return IntentDecision(
                route=Route.TAG,
                reason="Concrete selector + lookup intent",
                confidence=0.98
            )

        # ---- Gate 3: Ambiguous → LLM ----
        return IntentDecision(
            route=Route.LLM,
            reason="No deterministic lookup signal",
            confidence=0.90
        )