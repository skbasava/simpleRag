import os
import logging
from typing import List, Optional

from qgenie.integrations.langchain import QGenieEmbeddings
from qgenie.client import QGenieClient
from qgenie.types import ChatMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

QGENIE_API_KEY = os.getenv("QGENIE_API_KEY")


# ---------------------------------------------------------
# 1. LLM wrapper (HyDE-lite)
# ---------------------------------------------------------
class HydeLLM:
    """
    Generates a hypothetical document (HyDE-lite)
    """

    def __init__(self):
        self.client = QGenieClient(api_key=QGENIE_API_KEY)

    def rewrite(self, user_query: str) -> str:
        system_prompt = (
            "You are an expert technical assistant.\n"
            "Rewrite the user query into a short, factual paragraph "
            "that would appear in the documentation answering it.\n"
            "Do NOT mention that this is a rewrite.\n"
            "Do NOT ask questions.\n"
        )

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_query),
        ]

        resp = self.client.chat(
            messages=messages,
            max_tokens=200,
            temperature=0.2,
        )

        text = resp.output_text.strip()
        logger.info("HyDE text generated")
        return text


# ---------------------------------------------------------
# 2. Embedding wrapper (SAFE)
# ---------------------------------------------------------
class QueryEmbedder:
    """
    Generates embeddings for a SINGLE query string.
    """

    def __init__(self, model: str = "stella_en_400M_v5"):
        self.emb = QGenieEmbeddings(
            api_key=QGENIE_API_KEY,
            model=model,
        )

    def embed(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        # IMPORTANT: pass a SINGLE string
        vectors = self.emb.embed_query(text)

        if not vectors:
            raise RuntimeError("Empty embedding returned")

        return vectors


# ---------------------------------------------------------
# 3. Public API (what your pipeline calls)
# ---------------------------------------------------------
class RagQueryEncoder:
    """
    Input: user query
    Output: vector embedding
    """

    def __init__(self):
        self.hyde = HydeLLM()
        self.embedder = QueryEmbedder()

    def encode(self, user_query: str) -> List[float]:
        logger.info("User query: %s", user_query)

        hyde_text = self.hyde.rewrite(user_query)
        logger.info("HyDE text: %s", hyde_text)

        vector = self.embedder.embed(hyde_text)
        logger.info("Embedding dimension: %d", len(vector))

        return vector


# ---------------------------------------------------------
# 4. Manual test
# ---------------------------------------------------------
if __name__ == "__main__":
    encoder = RagQueryEncoder()

    vec = encoder.encode(
        "Give me the policy for address 0xc2630000 in project Kaanapalli"
    )

    print("Vector size:", len(vec))