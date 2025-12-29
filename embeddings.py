from dataclasses import dataclass
from typing import List, Optional
import logging

# QGenie SDK imports (adjust path if needed)
from qgenie import QGenieEmbedding, QGenieEmbeddingConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingConfig:
    """
    Configuration for embedding generation.
    """
    model: str = "stella_en_400M_v5"
    batch_size: int = 16
    timeout_sec: int = 60


class Embedder:
    """
    Single-responsibility class to generate embeddings.
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()

        self._client = QGenieEmbedding(
            config=QGenieEmbeddingConfig(
                model=self.config.model,
                batch_size=self.config.batch_size,
                timeout_sec=self.config.timeout_sec,
            )
        )

        logger.info(
            "Embedder initialized",
            extra={
                "model": self.config.model,
                "batch_size": self.config.batch_size,
            },
        )

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text input.
        """
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        try:
            vector = self._client.embed_fn(text)

            if not vector:
                raise RuntimeError("Empty embedding returned")

            logger.debug("Embedding generated", extra={"dim": len(vector)})
            return vector

        except Exception as exc:
            logger.exception("Embedding generation failed")
            raise RuntimeError("Embedding generation failed") from exc

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        """
        if not texts:
            return []

        try:
            vectors = self._client.embed_fn(texts)

            if len(vectors) != len(texts):
                raise RuntimeError("Embedding count mismatch")

            logger.debug(
                "Batch embedding generated",
                extra={"count": len(vectors), "dim": len(vectors[0])},
            )
            return vectors

        except Exception as exc:
            logger.exception("Batch embedding generation failed")
            raise RuntimeError("Batch embedding generation failed") from exc