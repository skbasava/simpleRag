from typing import List
from app.rag.models import Chunk
from app.rag.context_resolver import ContextResult


class PromptBuilder:
    """
    Builds a grounded, deterministic prompt for policy RAG.
    """

    SYSTEM_PROMPT = """\
You are a Security Access Policy Expert.

Rules:
- Use ONLY the provided policy context.
- Do NOT invent policies.
- If information is missing, say so clearly.
- Respect project, version, and profile boundaries.
- When comparing policies, list differences explicitly.
- When answering ranges, always show start/end addresses.
"""

    def build(
        self,
        user_query: str,
        context: ContextResult,
        chunks: List[Chunk],
    ) -> str:
        """
        Build final prompt for LLM.
        """

        header = self._build_header(context)
        policy_context = self._build_policy_context(chunks)
        question = self._build_question(user_query)

        return "\n\n".join([
            self.SYSTEM_PROMPT,
            header,
            policy_context,
            question,
        ])

    # -----------------------------
    # Header
    # -----------------------------

    def _build_header(self, context: ContextResult) -> str:
        lines = [
            "### Request Context",
            f"- Project: {context.project}",
            f"- Version: {context.version}",
        ]

        if context.profile:
            lines.append(f"- Profile: {context.profile}")

        if context.mpu:
            lines.append(f"- MPU: {context.mpu}")

        return "\n".join(lines)

    # -----------------------------
    # Policy Context
    # -----------------------------

    def _build_policy_context(self, chunks: List[Chunk]) -> str:
        if not chunks:
            return "### Policy Context\n(No matching policy chunks found)"

        lines = ["### Policy Context"]

        for i, chunk in enumerate(chunks, start=1):
            lines.append(self._format_chunk(i, chunk))

        return "\n\n".join(lines)

    def _format_chunk(self, idx: int, chunk: Chunk) -> str:
        return f"""\
Policy {idx}:
- Project: {chunk.project}
- MPU: {chunk.mpu_name}
- RG Index: {chunk.rg_index}
- Profile: {chunk.profile}
- Address Range: {chunk.start_hex} – {chunk.end_hex}
- Source: {chunk.source}

Policy Text:
{chunk.chunk_text}
"""

    # -----------------------------
    # Question
    # -----------------------------

    def _build_question(self, user_query: str) -> str:
        return f"""\
### User Question
{user_query}

### Answer Instructions
- Answer concisely.
- Cite policy numbers when relevant.
- If multiple policies apply, summarize them.
"""