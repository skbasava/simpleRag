from dataclasses import dataclass
from typing import Optional

@dataclass
class RAGSession:
    project: Optional[str] = None
    version: Optional[str] = None
