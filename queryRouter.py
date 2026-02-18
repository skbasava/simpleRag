import re
from enum import Enum

class RouteType(str, Enum):
    TAG = "TAG"
    LLM = "LLM"

class QueryRouter:
    # Patterns for technical retrieval
    TAG_PATTERNS = [
        r"polic(?:y|ies)", r"mpus?", r"regions?", r"projects?",
        r"address(?:es)?", r"profiles?", r"counts?", r"lists?", r"versions?"
    ]
    
    # Phrases that signal a request for an explanation (Conceptual Intent)
    LLM_INTENT_PATTERNS = [
        r"\bwhy\b", r"\bhow\b", r"\bexplain\b", r"\bdifference\b", r"\bwhat is\b"
    ]

    # Combine into compiled regex for performance
    # Uses lookarounds to allow underscores (like CNOC_MPU) but block sub-words (like "discount")
    TAG_REGEX = re.compile(
        rf"(?<![a-zA-Z0-9])(?:{'|'.join(TAG_PATTERNS)})(?![a-zA-Z0-9])", 
        re.IGNORECASE
    )
    
    LLM_REGEX = re.compile(
        rf"(?:{'|'.join(LLM_INTENT_PATTERNS)})", 
        re.IGNORECASE
    )

    @classmethod
    def route(cls, query: str) -> RouteType:
        # 1. Intent Check: If they ask "Why" or "How", always send to LLM
        if cls.LLM_REGEX.search(query):
            return RouteType.LLM
            
        # 2. Keyword/Address Check: If no "Why/How", check for TAG keywords
        if cls.TAG_REGEX.search(query) or "0x" in query.lower():
            return RouteType.TAG

        # 3. Default
        return RouteType.LLM