# main.py
from planner import Planner
from executor import Executor
from embeddings import Embedder   # your existing embedder


def main():
    user_query = "What are the address range covered by MPU AOSS_PERIPH_MPU_XPU4 in Kaanapalli?"

    # Step 1: Instructor / parser output (already working in your code)
    parsed_intent = {
        "project": "Kaanapalli",
        "mpu": "AOSS_PERIPH_MPU_XPU4",
        "version": None,
        "addr_contains": None,
        "question": user_query
    }

    # Step 2: Build plan
    planner = Planner()
    plan = planner.build_plan(parsed_intent)

    # Step 3: Execute
    executor = Executor(embedder=Embedder())
    for step in plan:
        if step["action"] == "CLARIFY":
            print(step["params"]["question"])
            return
        if step["action"] == "HYBRID_SEARCH":
            result = executor.run(
                step["params"]["semantic_query"],
                step["params"]["filters"]
            )
            print(result)


if __name__ == "__main__":
    main()