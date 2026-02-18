import re
from enum import Enum


class RouteType(str, Enum):
    TAG = "TAG"
    LLM = "LLM"


class QueryRouter:

    # 1. Handle Plurals: Use regex syntax for variations
    # 'polic(?:y|ies)' matches "policy" or "policies"
    # 'regions?' matches "region" or "regions"
    # 'address(?:es)?' matches "address" or "addresses"
    TAG_KEYWORDS_REGEX = [
        r"polic(?:y|ies)",
        r"mpu",
        r"regions?",
        r"address(?:es)?",
        r"profiles?",
        r"counts?",
        r"lists?",
        r"versions?",
    ]

    # 2. Custom Boundaries: Instead of \b, we use (?<![a-zA-Z0-9]) and (!?[a-zA-Z0-9])
    # This means "only trigger if the keyword is NOT surrounded by other letters/numbers".
    # This allows underscores or hyphens to act as valid boundaries (catching CNOC_SS_MPU).
    KEYWORD_PATTERN = re.compile(
        rf"(?<![a-zA-Z0-9])(?:{'|'.join(TAG_KEYWORDS_REGEX)})(?![a-zA-Z0-9])", 
        re.IGNORECASE
    )

    ADDRESS_PATTERN = re.compile(r"(?<![a-zA-Z0-9])0x[0-9a-f]+(?![a-zA-Z0-9])", re.IGNORECASE)

    @classmethod
    def route(cls, query: str) -> RouteType:
        if cls.ADDRESS_PATTERN.search(query) or cls.KEYWORD_PATTERN.search(query):
            return RouteType.TAG
        return RouteType.LLM
