# rag/classifier.py
from enum import Enum
import re


class QueryType(str, Enum):
    SEMANTIC = "semantic"
    STRUCTURED = "structured"
    HYBRID = "hybrid"


STRUCTURED_PATTERNS = [
    r"\b(start|end|address|range)\b",
    r"\bmpu\b",
    r"\bprofile\b",
    r"\bproject\b",
    r"\bversion\b",
    r"\bxpu\b",
    r"\brg_index\b",
]


def classify_query(query: str) -> QueryType:
    q = query.lower()

    structured_hits = sum(
        1 for p in STRUCTURED_PATTERNS if re.search(p, q)
    )

    semantic_hits = len(q.split()) > 5

    if structured_hits and semantic_hits:
        return QueryType.HYBRID
    if structured_hits:
        return QueryType.STRUCTURED
    return QueryType.SEMANTIC
