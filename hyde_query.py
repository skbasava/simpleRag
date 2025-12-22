"""
HyDE-based query embedding pipeline

Contract:
Input  : user_query (str)
Output : embedding vector (List[float])

Flow:
User Query
→ HyDE rewrite (LLM)
→ Combine (user + rewrite)
→ Embed
→ Vector
"""

from typing import List


# -----------------------------
# Interfaces (minimal contracts)
# -----------------------------

class LLMClient:
    """
    Minimal LLM interface.
    Replace implementation with Groq / OpenAI / QGenie etc.
    """
    def complete(self, prompt: str) -> str:
        raise NotImplementedError


class Embedder:
    """
    Minimal embedder interface.
    """
    def embed(self, text: str) -> List[float]:
        raise NotImplementedError


# -----------------------------
# HyDE prompt builder
# -----------------------------

def build_hyde_prompt(user_query: str) -> str:
    """
    Build a SAFE HyDE prompt:
    - No hallucination
    - No new facts
    - Preserve addresses and technical terms
    """
    return f"""
You are a query rewriting engine.
Rewrite the user query into a dense factual search query.
Do NOT add new facts.
Do NOT invent values.
Preserve addresses and technical terms.

User Query:
{user_query}

Rewritten Query:
""".strip()


# -----------------------------
# HyDE → Embedding pipeline
# -----------------------------

class HydeQueryEmbedder:
    """
    Produces an embedded vector for a user query using HyDE.
    """

    def __init__(self, llm: LLMClient, embedder: Embedder):
        self.llm = llm
        self.embedder = embedder

    def embed_query(self, user_query: str) -> List[float]:
        # 1. Build HyDE prompt
        hyde_prompt = build_hyde_prompt(user_query)

        # 2. Get HyDE rewrite
        rewritten = self.llm.complete(hyde_prompt).strip()

        # Safety fallback
        if not rewritten:
            rewritten = user_query

        # 3. Build final embedding text
        final_text = f"""
User intent:
{user_query}

Search intent:
{rewritten}
""".strip()

        # Debug hooks (keep while developing)
        print("=== HYDE DEBUG ===")
        print("User Query:", user_query)
        print("HyDE Rewrite:", rewritten)
        print("Embedding Text (first 300 chars):")
        print(final_text[:300])
        print("==================")

        # 4. Embed
        vector = self.embedder.embed(final_text)

        return vector


# -----------------------------
# Example dummy implementations
# (Replace these in real usage)
# -----------------------------

class DummyLLM(LLMClient):
    def complete(self, prompt: str) -> str:
        # VERY naive placeholder
        # Replace with real LLM call
        return "MPU region configuration that covers the specified address"


class DummyEmbedder(Embedder):
    def embed(self, text: str) -> List[float]:
        # Fake vector for demonstration
        return [0.0] * 1024


# -----------------------------
# Manual test
# -----------------------------

if __name__ == "__main__":
    llm = DummyLLM()
    embedder = DummyEmbedder()

    hyde_embedder = HydeQueryEmbedder(llm, embedder)

    vector = hyde_embedder.embed_query(
        "In which MPU the given address 0xc2630000 is covered?"
    )

    print("Vector dimension:", len(vector))