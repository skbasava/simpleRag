from typing import List
from app.rag.models import Chunk

class ChunkMerger:
    @staticmethod
    def merge(structured: List[Chunk], semantic: List[Chunk]) -> List[Chunk]:
        seen = set()
        merged: List[Chunk] = []

        for chunk in structured + semantic:
            key = (chunk.project, chunk.mpu_name, chunk.rg_index, chunk.profile)

            if key in seen:
                continue

            seen.add(key)
            merged.append(chunk)

        return merged