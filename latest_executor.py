from typing import List, Dict, Any, Optional
from rag.db.psql import SQLQueryEngine
from rag.db.vectors import VectorRepo
from rag.db.policy_classifier import classify_policy
from rag.llm.llm_client import LLMClient


class Executor:
    """
    Executes planner-generated plans deterministically.
    """

    def __init__(self, sql: SQLQueryEngine, vector: VectorRepo, llm: LLMClient):
        self.sql = sql
        self.vector = vector
        self.llm = llm

        # execution memory
        self.results: Dict[int, Any] = {}

    # -------------------------------------------------
    # Main entry
    # -------------------------------------------------

    def run(self, plan: List[Dict]) -> List[Dict]:
        for idx, step in enumerate(plan):
            action = step["action"]

            # dependency check
            if not self._deps_satisfied(step):
                continue

            if action == "SQL_SEARCH":
                self.results[idx] = self._sql_search(step["params"])

            elif action == "VECTOR_SEARCH":
                self.results[idx] = self._vector_search(step["params"])

            elif action == "CLARIFY":
                self.results[idx] = step["params"]
                break

            else:
                raise ValueError(f"Unknown planner action: {action}")

        return self._final_result()

    # -------------------------------------------------
    # Action handlers
    # -------------------------------------------------

    def _sql_search(self, params: Dict) -> List[Dict]:
        rows = self.sql.fetch_policies(params)

        # classify policies (pure function)
        for r in rows:
            cls = classify_policy(
                r["addr_start"],
                r["addr_end"],
                r["profile"]
            )
            r.update(cls)

        return rows

    def _vector_search(self, params: Dict) -> List[Dict]:
        """
        Vector search ONLY runs if prior SQL result is empty.
        """
        if self._has_prior_results():
            return []

        return self.vector.semantic_search(
            query_text=params["semantic_query"],
            filters=params,
            top_k=params.get("top_k", 10)
        )

    # -------------------------------------------------
    # Helpers
    # -------------------------------------------------

    def _deps_satisfied(self, step: Dict) -> bool:
        for dep in step.get("depends_on", []):
            if not self.results.get(dep):
                return True  # empty SQL → allow fallback
        return True

    def _has_prior_results(self) -> bool:
        for res in self.results.values():
            if isinstance(res, list) and res:
                return True
        return False

    def _final_result(self) -> List[Dict]:
        """
        Return the first non-empty result set.
        """
        for res in self.results.values():
            if isinstance(res, list) and res:
                return res
        return []