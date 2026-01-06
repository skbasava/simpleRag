from typing import Optional, List
from pydantic import BaseModel, Field 

from enum import Enum


class Intent(str, Enum):
    POLICY   = "POLICY"     # MPU / policy / region related
    CATALOG  = "CATALOG"    # projects, versions, supported lists
    EXPLAIN  = "EXPLAIN"    # explain policies / behavior
    VALIDATE = "VALIDATE"   # check access / allowed / denied
    UNKNOWN  = "UNKNOWN"

class Operation(str, Enum):
    LOOKUP   = "LOOKUP"     # retrieve rows
    COUNT    = "COUNT"      # aggregate
    LIST     = "LIST"       # enumerate
    COMPARE  = "COMPARE"    # diff between versions / projects
    EXPLAIN  = "EXPLAIN"    # explanation-only

class Entity(str, Enum):
    POLICY         = "POLICY"          # xml_chunks
    PROJECT        = "PROJECT"         # project_versions
    VERSION        = "VERSION"
    MPU            = "MPU"
    REGION         = "REGION"
    ADDRESS        = "ADDRESS"


class QueryFacts(BaseModel):
    """
    Structured facts extracted from user query
    via Instructor (LLM-based extraction).

    This class is the ONLY contract between:
        Instructor → Planner → Executors
    """

    # ---- Core routing ----
    intent: Intent = Field(
        default=Intent.UNKNOWN,
        description="High-level intent of the user query"
    )

    operation: Operation = Field(
        default=Operation.LOOKUP,
        description="Operation to perform on the data"
    )

    entity: Entity = Field(
        default=Entity.POLICY,
        description="Primary entity the query refers to"
    )

    # ---- Scope filters ----
    project: Optional[str] = Field(
        default=None,
        description="Project / SoC name"
    )

    version: Optional[str] = Field(
        default=None,
        description="Project version; if None, planner resolves latest"
    )

    mpu_name: Optional[str] = Field(
        default=None,
        description="MPU or XPU name"
    )

    # ---- Address semantics ----
    addr_start: Optional[int] = Field(
        default=None,
        description="Start address (point or range)"
    )

    addr_end: Optional[int] = Field(
        default=None,
        description="End address for range queries"
    )

    # ---- Policy semantics ----
    profile: Optional[str] = Field(
        default=None,
        description="Security profile (TZ, HYP, MSA, NON_STATIC, etc.)"
    )

    dynamic_policy: Optional[bool] = Field(
        default=None,
        description="True if policy is runtime-programmable"
    )

    # ---- Raw references ----
    raw_query: Optional[str] = Field(
        default=None,
        description="Original user query text"
    )

    hyde_text: Optional[str] = Field(
        default=None,
        description="HyDE rewritten semantic query"
    )

    # ---- Safety flags ----
    missing_required_fields: Optional[List[str]] = Field(
        default=None,
        description="Fields missing for execution"
    )