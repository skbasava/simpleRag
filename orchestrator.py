from rag.query_helpers.hyde_query import HydeQueryBuilder
from rag.query_helpers.query_facts import extract_query_facts
from rag.planner import Planner
from rag.executors import Executor
from rag.db.psql import SQLQueryEngine
from rag.db.vectors import VectorRepo
from rag.llm.llm_client import LLMClient
from rag.llm.embeddings import QueryEmbedder


class RAGOrchestrator:
    """
    Single entry point for the RAG pipeline.
    """

    def __init__(self):
        self.embedder = QueryEmbedder()
        self.sql = SQLQueryEngine()
        self.vector = VectorRepo(self.sql.get_connection(), self.embedder)
        self.llm = LLMClient()

        self.planner = Planner()
        self.executor = Executor(
            sql=self.sql,
            vector=self.vector,
            llm=self.llm
        )

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------

    def run(self, user_query: str) -> str:
        # 1️⃣ HyDE rewrite
        hyde_text = HydeQueryBuilder().rewrite(user_query)

        # 2️⃣ Extract structured facts
        facts = extract_query_facts(user_query, hyde_text)

        # 3️⃣ Build execution plan
        plan = self.planner.plan(facts)

        # 4️⃣ Execute plan
        rows = self.executor.run(plan)

        # 5️⃣ Final answer synthesis
        return self._synthesize_answer(user_query, rows)

    # -------------------------------------------------
    # LLM Answer Generation
    # -------------------------------------------------

    def _synthesize_answer(self, question: str, rows: list) -> str:
        if not rows:
            return "No matching MPU policies were found."

        context_blocks = []
        for r in rows:
            block = (
                f"MPU: {r['mpu_name']}\n"
                f"Region: {r['rg_index']}\n"
                f"Policy: {r['policy_type']}\n"
                f"Address: {r['address']}\n"
                f"Note: {r['explanation']}"
            )
            context_blocks.append(block)

        context = "\n\n".join(context_blocks)

        return self.llm.ask_llm(
            question=question,
            context=context
        )