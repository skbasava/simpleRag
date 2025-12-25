"""
rag_pipeline_demo.py

Single-file minimal RAG pipeline with:
- HyDE semantic rewrite
- Instructor-based fact extraction
- Dependency-aware query planner
- Hybrid executor (pgvector + SQL-style filters)

This file intentionally mocks external services (LLM, pgvector)
to keep logic crystal-clear.
"""

from typing import Optional, List, Dict
from dataclasses import dataclass
import re
import json

# ============================================================
# 1. Query Facts (Instructor output schema)
# ============================================================

@dataclass
class QueryFacts:
    project: Optional[str] = None
    version: Optional[str] = None
    mpu_name: Optional[str] = None
    addr_start: Optional[int] = None
    profile: Optional[str] = None


# ============================================================
# 2. HyDE (Semantic rewrite)
# ============================================================

def hyde_rewrite(user_query: str) -> str:
    """
    Simulated HyDE rewrite.
    In real system, this comes from LLM.
    """
    return (
        "The query requests the MPU access-control policy that governs the "
        "I/O memory region at address 0x0C400000 within project kaanapalli.\n"
        "[PROJECT=kaanapalli]\n"
        "[ADDR_START=0x0C400000]"
    )


def extract_semantic_query(hyde_text: str) -> str:
    """
    Extract natural-language semantic intent from HyDE output.
    """
    semantic_lines = []
    for line in hyde_text.splitlines():
        if line.startswith("["):
            break
        semantic_lines.append(line.strip())

    return " ".join(semantic_lines)


# ============================================================
# 3. Instructor (FACT extraction only)
# ============================================================

def extract_query_facts(user_query: str, hyde_text: str) -> QueryFacts:
    """
    Mimics Instructor:
    - Validates
    - Extracts ONLY structured facts
    - Does NOT generate plans or semantics
    """

    facts = QueryFacts()

    # PROJECT
    m = re.search(r"\[PROJECT=(.*?)\]", hyde_text)
    if m:
        facts.project = m.group(1)

    # ADDRESS
    m = re.search(r"\[ADDR_START=(0x[a-fA-F0-9]+)\]", hyde_text)
    if m:
        facts.addr_start = int(m.group(1), 16)

    # VERSION (default policy)
    facts.version = "latest"

    return facts


# ============================================================
# 4. Planner
# ============================================================

class QueryPlanner:
    """
    Planner decides *HOW* to search, never *WHAT* to search.
    """

    def plan(self, semantic_query: str, facts: QueryFacts) -> List[Dict]:
        plans = []

        if not facts.project:
            plans.append({
                "qid": 1,
                "action": "CLARIFY",
                "params": {
                    "question": "Which project is this policy for?"
                },
                "depends": []
            })
            return plans

        plans.append({
            "qid": 1,
            "action": "HYBRID_SEARCH",
            "params": {
                "semantic_query": semantic_query,
                "filters": {
                    "project": facts.project,
                    "version": facts.version,
                    "addr_contains": facts.addr_start
                }
            },
            "depends": []
        })

        return plans


# ============================================================
# 5. Executor
# ============================================================

class Executor:
    """
    Executes plans produced by planner.
    """

    def embed(self, text: str) -> List[float]:
        """
        Fake embedding generator.
        """
        return [float(len(text))] * 5

    def hybrid_search(self, semantic_query: str, filters: Dict):
        """
        Simulated pgvector + SQL hybrid search.
        """
        embedding = self.embed(semantic_query)

        print("\n[EXECUTOR]")
        print("Semantic query:", semantic_query)
        print("Embedding:", embedding)
        print("SQL filters:", filters)

        # Mock result
        return [{
            "project": filters["project"],
            "version": filters["version"],
            "summary": "AOSS MPU policy allowing TME_FW access",
            "confidence": 0.91
        }]

    def run_plan(self, plans: List[Dict]):
        for p in plans:
            if p["action"] == "CLARIFY":
                print("\n[CLARIFICATION REQUIRED]")
                print(p["params"]["question"])
                return None

            if p["action"] == "HYBRID_SEARCH":
                return self.hybrid_search(
                    p["params"]["semantic_query"],
                    p["params"]["filters"]
                )


# ============================================================
# 6. Main (Test)
# ============================================================

def main():
    user_query = "Give me the policy for address 0x0C400000 in project kaanapalli"

    print("\n[USER QUERY]")
    print(user_query)

    # HyDE
    hyde_text = hyde_rewrite(user_query)
    print("\n[HyDE OUTPUT]")
    print(hyde_text)

    semantic_query = extract_semantic_query(hyde_text)
    print("\n[SEMANTIC QUERY]")
    print(semantic_query)

    # Instructor
    facts = extract_query_facts(user_query, hyde_text)
    print("\n[FACTS]")
    print(json.dumps(facts.__dict__, indent=2))

    # Planner
    planner = QueryPlanner()
    plans = planner.plan(semantic_query, facts)
    print("\n[PLANS]")
    print(json.dumps(plans, indent=2))

    # Executor
    executor = Executor()
    results = executor.run_plan(plans)

    print("\n[RESULTS]")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()