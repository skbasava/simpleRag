"""
router.py

Deterministic query router for TAG-based RAG system.
Uses Instructor (QueryFacts) as the single source of truth.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any

from rag.query_helpers.hyde_query import HydeRewriter
from rag.query_helpers.query_facts import QueryFacts
from rag.orchestrator import RagOrchestrator
from rag.llm.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Route Types
# ------------------------------------------------------------------

class RouteType(Enum):
    TAG = "tag"   # SQL + explainability + K-shot + grounded answer
    LLM = "llm"   # General purpose answer (no DB grounding)


# ------------------------------------------------------------------
# Router Response
# ------------------------------------------------------------------

@dataclass
class RouterResponse:
    success: bool
    answer: str
    route_type: RouteType
    facts: Optional[QueryFacts]
    sql_rows: Optional[list] = None
    metadata: Optional[dict] = None
    error: Optional[str] = None


# ------------------------------------------------------------------
# Query Router
# ------------------------------------------------------------------

class QueryRouter:
    """
    QueryRouter for MPU TAG system.

    Routing principles:
    - Instructor (QueryFacts) decides intent
    - Intent decides route (TAG vs LLM)
    - Router NEVER guesses intent
    - TAG answers MUST come from SQL
    """

    def __init__(
        self,
        orchestrator: RagOrchestrator,
        llm_client: LLMClient,
        hyde: Optional[HydeRewriter] = None,
    ):
        self.orchestrator = orchestrator
        self.llm = llm_client
        self.hyde = hyde or HydeRewriter()

    # --------------------------------------------------------------
    # Public API (LibreChat will call this)
    # --------------------------------------------------------------

    async def route(self, user_query: str) -> RouterResponse:
        """
        Main entrypoint.
        """
        try:
            logger.info("Routing query")

            # 1. HyDE rewrite
            hyde_text = self.hyde.rewrite(user_query)

            # 2. Instructor extraction (INTENT CLASSIFIER)
            facts: QueryFacts = self.orchestrator._extract_facts(
                user_query=user_query,
                hyde_text=hyde_text,
            )

            logger.info(
                "QueryFacts extracted",
                extra={"intent": facts.intent, "project": facts.project},
            )

            # 3. Decide route
            route = self._decide_route(facts)

            # 4. Execute route
            if route == RouteType.TAG:
                return await self._handle_tag(user_query, hyde_text, facts)

            return await self._handle_llm(user_query, facts)

        except Exception as e:
            logger.exception("Router failure")
            return RouterResponse(
                success=False,
                answer="Internal routing error",
                route_type=RouteType.LLM,
                facts=None,
                error=str(e),
            )

    # --------------------------------------------------------------
    # Routing Decision (DETERMINISTIC)
    # --------------------------------------------------------------

    def _decide_route(self, facts: QueryFacts) -> RouteType:
        """
        Deterministic mapping from Instructor intent → backend.
        """
        if facts.intent in {
            "REGION_LOOKUP",
            "PROFILE_LOOKUP",
        }:
            return RouteType.TAG

        return RouteType.LLM

    # --------------------------------------------------------------
    # TAG Handler (Your RAG System)
    # --------------------------------------------------------------

    async def _handle_tag(
        self,
        user_query: str,
        hyde_text: str,
        facts: QueryFacts,
    ) -> RouterResponse:
        """
        Execute SQL/TAG pipeline.
        """

        logger.info("Executing TAG route")

        # Orchestrator already:
        # - Builds plan
        # - Runs SQL
        # - Explains region choice
        # - Builds K-shot prompt
        # - Calls LLM
        result = self.orchestrator.run_with_facts(
            user_query=user_query,
            hyde_text=hyde_text,
            query_facts=facts,
        )

        if result is None:
            return RouterResponse(
                success=False,
                answer="No matching MPU data found.",
                route_type=RouteType.TAG,
                facts=facts,
            )

        return RouterResponse(
            success=True,
            answer=result.answer,
            route_type=RouteType.TAG,
            facts=facts,
            sql_rows=result.sql_rows,
            metadata={
                "explanation": result.explanation,
                "confidence": result.confidence,
            },
        )

    # --------------------------------------------------------------
    # LLM Handler (Fallback / General Q&A)
    # --------------------------------------------------------------

    async def _handle_llm(
        self,
        user_query: str,
        facts: QueryFacts,
    ) -> RouterResponse:
        """
        Plain LLM answer (no TAG).
        """

        logger.info("Executing LLM route")

        response = await self.llm.ask_llm(
            prompt=user_query,
            temperature=0.3,
            max_tokens=1024,
        )

        if not response.success:
            return RouterResponse(
                success=False,
                answer="LLM failed to generate response",
                route_type=RouteType.LLM,
                facts=facts,
                error=response.error,
            )

        return RouterResponse(
            success=True,
            answer=response.answer,
            route_type=RouteType.LLM,
            facts=facts,
            metadata={"model": response.model},
        )