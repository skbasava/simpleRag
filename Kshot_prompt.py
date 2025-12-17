from typing import List, Optional
from app.rag.models import Chunk


class PromptBuilder:
    """
    Builds the final prompt sent to the LLM.
    This class is the ONLY place where raw context is transformed into text.
    """

    def build(
        self,
        *,
        user_query: str,
        rewritten_query: Optional[str],
        chunks: List[Chunk],
        kshot_examples: Optional[List[str]] = None,
        confidence_hint: Optional[str] = None,
    ) -> str:
        """
        Build a grounded, non-hallucinating prompt.
        """

        system_instructions = self._system_instructions()
        examples_block = self._examples_block(kshot_examples)
        context_block = self._context_block(chunks)
        query_block = self._query_block(user_query, rewritten_query)
        confidence_block = self._confidence_block(confidence_hint)

        prompt = "\n\n".join(
            block
            for block in [
                system_instructions,
                examples_block,
                context_block,
                query_block,
                confidence_block,
            ]
            if block
        )

        return prompt.strip()

    # -------------------------
    # Prompt sections
    # -------------------------

    def _system_instructions(self) -> str:
        return (
            "You are a hardware security and access-control policy expert.\n\n"
            "Rules:\n"
            "1. Answer ONLY using the provided policy context.\n"
            "2. Do NOT invent MPU names, RG indices, address ranges, or profiles.\n"
            "3. If the answer is not present in the context, say:\n"
            "   \"The policy data does not specify this information.\"\n"
            "4. Cite MPU name, RG index, profile, and address range explicitly.\n"
            "5. Be precise and concise.\n"
        )

    def _examples_block(self, examples: Optional[List[str]]) -> Optional[str]:
        if not examples:
            return None

        formatted = "\n\n".join(
            f"Example {i+1}:\n{ex}"
            for i, ex in enumerate(examples)
        )

        return f"Validated examples:\n{formatted}"

    def _context_block(self, chunks: List[Chunk]) -> str:
        if not chunks:
            return (
                "Policy context:\n"
                "No policy chunks were retrieved for this query."
            )

        rendered_chunks = []
        for c in chunks:
            rendered_chunks.append(
                f"""
[Policy Chunk {c.chunk_id}]
Project: {c.project}
Version: {c.version}
MPU: {c.mpu_name}
RG Index: {c.rg_index}
Profile: {c.profile}
Address Range: {c.start_hex} - {c.end_hex}

Policy Text:
{c.chunk_text}
""".strip()
            )

        return "Policy context:\n" + "\n\n".join(rendered_chunks)

    def _query_block(
        self,
        user_query: str,
        rewritten_query: Optional[str],
    ) -> str:
        if rewritten_query and rewritten_query != user_query:
            return (
                f"User question:\n{user_query}\n\n"
                f"Interpreted intent:\n{rewritten_query}"
            )

        return f"User question:\n{user_query}"

    def _confidence_block(self, confidence_hint: Optional[str]) -> Optional[str]:
        if not confidence_hint:
            return None

        return (
            "Confidence guidance:\n"
            f"The retrieved context confidence is: {confidence_hint}.\n"
            "If confidence is low, respond cautiously."
        )