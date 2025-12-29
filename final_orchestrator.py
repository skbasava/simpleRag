from __future__ import annotations

import logging
from typing import Any

from instructor import patch, Mode

from qgenie import QGenieClient, QGenieOpenAIClient

from rag.query_helpers.hyde_query import HyDEQueryBuilder
from rag.query_helpers.qgenie_instruct import extract_query_facts
from rag.query_helpers.chunk import QueryFacts

from rag.planner import Planner, ExecutionPlan
from rag.executors import Executor


logger = logging.getLogger("rag.orchestrator")


class Orchestrator:
    """
    Coordinates:
      1. HyDE rewrite
      2. Structured fact extraction (Instructor)
      3. Planning
      4. Execution

    This module DOES NOT:
      - decide SQL vs VECTOR
      - execute queries directly
      - mutate plans
    """

    def __init__(
        self,
        planner: Planner,
        executor: Executor,
        hyde_writer: HyDEQueryBuilder,
    ):
        self.planner = planner
        self.executor = executor
        self.hyde_writer = hyde_writer

    # ---------------------------------------------------------
    # Public entrypoint
    # ---------------------------------------------------------

    def run(self, user_query: str) -> Any:
        logger.info("Received user query")
        logger.debug("User query: %s", user_query)

        # -----------------------------------------------------
        # 1. HyDE rewrite
        # -----------------------------------------------------

        hyde_text = self._hyde_rewrite(user_query)

        # -----------------------------------------------------
        # 2. Extract structured facts (Instructor)
        # -----------------------------------------------------

        query_facts = self._extract_facts(user_query, hyde_text)

        # -----------------------------------------------------
        # 3. Build execution plan
        # -----------------------------------------------------

        plan = self._build_plan(query_facts)

        # -----------------------------------------------------
        # 4. Execute plan
        # -----------------------------------------------------

        return self._execute_plan(plan)

    # ---------------------------------------------------------
    # Internal steps
    # ---------------------------------------------------------

    def _hyde_rewrite(self, user_query: str) -> str:
        logger.debug("Starting HyDE rewrite")

        hyde_text = self.hyde_writer.embed_query(user_query)

        logger.debug("HyDE rewrite complete")
        logger.debug("HyDE text:\n%s", hyde_text)

        return hyde_text

    def _extract_facts(
        self,
        user_query: str,
        hyde_text: str,
    ) -> QueryFacts:
        logger.debug("Initializing Instructor client")

        raw_client = QGenieClient()
        openai_client = QGenieOpenAIClient(
            raw_client,
            default_model="llama3.1-8b",
        )

        instruct_client = patch(
            openai_client,
            mode=Mode.JSON_SCHEMA,
        )

        logger.debug("Extracting structured query facts")

        facts: QueryFacts = extract_query_facts(
            instruct_client,
            user_query,
            hyde_text,
        )

        logger.debug(
            "QueryFacts extracted:\n%s",
            facts.model_dump() if hasattr(facts, "model_dump") else facts,
        )

        return facts

    def _build_plan(self, facts: QueryFacts) -> ExecutionPlan:
        logger.debug("Building execution plan")

        plan = self.planner.plan(facts)

        logger.info("Execution plan created")
        logger.debug("Plan reason: %s", plan.reason)

        for idx, step in enumerate(plan.steps):
            logger.debug(
                "Plan step %d | action=%s | deps=%s | params=%s",
                idx,
                step.action,
                step.deps,
                step.params,
            )

        return plan

    def _execute_plan(self, plan: ExecutionPlan):
        logger.info("Executing plan")

        result = self.executor.run(plan)

        logger.info("Plan execution completed")
        logger.debug("Final result type: %s", type(result))

        return result