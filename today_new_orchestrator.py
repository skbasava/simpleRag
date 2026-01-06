import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class RagOrchestrator:
    """
    Production RAG Orchestrator.

    Pipeline:
        User Query
            ↓
        HyDE Rewrite
            ↓
        Instructor (extract QueryFacts)
            ↓
        Planner (decide execution plan)
            ↓
        Executors (SQL / COUNT / LIST / etc.)
            ↓
        Explainability + Confidence
            ↓
        LLM (final answer)
    """

    def __init__(
        self,
        hyde_generator,
        instructor,
        planner,
        executors,
        llm_client,
    ):
        self.hyde = hyde_generator
        self.instructor = instructor
        self.planner = planner
        self.executors = executors
        self.llm = llm_client

    # ----------------------------
    # Public Entry Point
    # ----------------------------
    def run(self, user_query: str) -> Dict[str, Any]:
        logger.info("Received query: %s", user_query)

        # 1️⃣ HYDE
        hyde_text = self._generate_hyde(user_query)

        # 2️⃣ Instructor → QueryFacts
        facts = self._extract_facts(user_query, hyde_text)

        # 3️⃣ Planner → ExecutionPlan
        plan = self._build_plan(facts)

        # 4️⃣ Execute plan
        execution_result = self._execute_plan(plan, facts)

        # 5️⃣ Build LLM context
        llm_context = self._build_llm_context(
            user_query=user_query,
            hyde_text=hyde_text,
            execution_result=execution_result,
        )

        # 6️⃣ Final Answer
        answer = self._ask_llm(llm_context)

        return {
            "answer": answer,
            "facts": facts.model_dump(),
            "plan": plan.model_dump(),
            "explainability": execution_result.get("explanation"),
            "confidence": execution_result.get("confidence"),
            "sources": execution_result.get("rows", []),
        }

    # ----------------------------
    # Step Implementations
    # ----------------------------
    def _generate_hyde(self, user_query: str) -> str:
        logger.debug("Generating HYDE text")
        hyde_text = self.hyde.generate(user_query)
        logger.debug("HYDE text: %s", hyde_text)
        return hyde_text

    def _extract_facts(self, user_query: str, hyde_text: str):
        logger.debug("Extracting QueryFacts using Instructor")
        facts = self.instructor.extract(
            user_query=user_query,
            hyde_text=hyde_text,
        )
        logger.debug("QueryFacts: %s", facts)
        return facts

    def _build_plan(self, facts):
        logger.debug("Building execution plan")
        plan = self.planner.plan(facts)
        logger.debug("ExecutionPlan: %s", plan)
        return plan

    def _execute_plan(self, plan, facts) -> Dict[str, Any]:
        logger.debug("Executing plan: %s", plan.operation)

        executor = self.executors.get(plan.operation)
        if not executor:
            raise RuntimeError(f"No executor found for operation: {plan.operation}")

        result = executor.execute(facts)

        logger.debug("Execution result rows: %d", len(result.get("rows", [])))
        logger.debug("Explainability: %s", result.get("explanation"))
        logger.debug("Confidence: %s", result.get("confidence"))

        return result

    def _build_llm_context(self, user_query: str, hyde_text: str, execution_result: Dict):
        logger.debug("Building LLM context")

        rows = execution_result.get("rows", [])

        sql_context = "\n".join(
            f"- {row.get('mpu_name')} [{hex(row.get('addr_start'))} - {hex(row.get('addr_end'))}]"
            for row in rows[:10]
        )

        context = f"""
User Query:
{user_query}

Relevant MPU Policy Records:
{sql_context}

Explanation:
{execution_result.get('explanation')}
"""

        logger.debug("LLM Context built")
        return context

    def _ask_llm(self, context: str) -> str:
        logger.debug("Calling LLM")
        response = self.llm.ask(
            system_prompt="You are an MPU policy expert assistant.",
            user_prompt=context,
        )
        logger.debug("LLM Response received")
        return response