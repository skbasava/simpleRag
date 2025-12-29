from rag.logging import get_logger
from rag.query_helpers.hyde_query import HyDEQueryBuilder
from rag.query_helpers.qgenie_instruct import extract_query_facts
from rag.planner import MPUPlanner
from rag.executors import SQLExecutor, VectorExecutor
from rag.llm.llm_client import LLMClient

logger = get_logger("rag.orchestrator")


class Orchestrator:
    def __init__(
        self,
        instruct_client,
        sql_executor: SQLExecutor,
        vector_executor: VectorExecutor,
        planner: MPUPlanner,
        llm: LLMClient,
    ):
        self.instruct_client = instruct_client
        self.sql = sql_executor
        self.vector = vector_executor
        self.planner = planner
        self.llm = llm

    def run(self, user_query: str) -> str:
        logger.info("Received user query")
        logger.debug("User query: %s", user_query)

        # --------------------------------------------------
        # 1. HyDE rewrite
        # --------------------------------------------------
        hyde = HyDEQueryBuilder()
        hyde_text = hyde.build(user_query)

        logger.info("HyDE rewrite generated")
        logger.debug("HyDE text:\n%s", hyde_text)

        # --------------------------------------------------
        # 2. Extract structured facts
        # --------------------------------------------------
        facts = extract_query_facts(
            self.instruct_client,
            user_query=user_query,
            hyde_text=hyde_text,
        )

        logger.info("QueryFacts extracted")
        logger.debug(
            "QueryFacts: %s",
            facts.model_dump() if hasattr(facts, "model_dump") else facts.dict(),
        )

        # --------------------------------------------------
        # 3. Planning
        # --------------------------------------------------
        plan = self.planner.plan(facts)

        logger.info("Execution plan created")
        logger.debug(
            "Plan strategy=%s | reason=%s | sql_filters=%s",
            plan.strategy,
            plan.reason,
            plan.sql_filters,
        )

        # --------------------------------------------------
        # 4. Execute plan
        # --------------------------------------------------
        rows = []

        if plan.strategy == "SQL":
            logger.info("Executing SQL strategy")
            rows = self.sql.fetch_policies(plan.sql_filters)
            logger.debug("SQL returned %d rows", len(rows))

        elif plan.strategy == "VECTOR":
            logger.info("Executing VECTOR strategy")
            rows = self.vector.search(facts)
            logger.debug("Vector search returned %d rows", len(rows))

        elif plan.strategy == "HYBRID":
            logger.info("Executing HYBRID strategy (SQL → VECTOR fallback)")

            rows = self.sql.fetch_policies(plan.sql_filters)
            logger.debug("SQL returned %d rows", len(rows))

            if not rows:
                logger.warning(
                    "SQL returned zero rows, falling back to vector search"
                )
                rows = self.vector.search(facts)
                logger.debug("Vector fallback returned %d rows", len(rows))

        else:
            logger.error("Unknown execution strategy: %s", plan.strategy)
            raise RuntimeError(f"Invalid planner strategy: {plan.strategy}")

        # --------------------------------------------------
        # 5. Context construction
        # --------------------------------------------------
        logger.info("Building LLM context blocks")

        context_blocks = []
        for idx, r in enumerate(rows):
            logger.debug(
                "Context row %d | MPU=%s | rg_index=%s",
                idx,
                r.get("mpu_name"),
                r.get("rg_index"),
            )
            context_blocks.append(self._build_context_block(r))

        context_text = "\n\n".join(context_blocks)

        logger.info(
            "Context prepared (%d blocks, %d chars)",
            len(context_blocks),
            len(context_text),
        )

        # --------------------------------------------------
        # 6. Ask LLM
        # --------------------------------------------------
        logger.info("Sending request to LLM")

        answer = self.llm.ask(
            question=user_query,
            context=context_text,
        )

        logger.info("LLM response generated")
        logger.debug("LLM answer:\n%s", answer)

        return answer

    def _build_context_block(self, row: dict) -> str:
        return (
            f"MPU: {row.get('mpu_name')}\n"
            f"Region: {row.get('rg_index')}\n"
            f"Address: {row.get('addr_start')} - {row.get('addr_end')}\n"
            f"Profile: {row.get('profile')}\n"
        )