from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Chunk:
    chunk_id: int
    project: str
    mpu_name: str
    rg_index: int
    profile: str
    start_hex: str
    end_hex: str
    chunk_text: str
    source: str        # "postgres" | "weaviate"
    score: Optional[float] = None