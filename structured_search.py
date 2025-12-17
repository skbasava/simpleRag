
from rag.models import RetrievedChunk

def fetch_chunks(pg, vector_hits, project=None, version=None):
    rows = pg.fetch(...)
    return [
        RetrievedChunk(
            chunk_text=r.chunk_text,
            project=r.project,
            version=r.version,
            profile=r.profile,
            mpu_name=r.mpu_name,
            rg_index=r.rg_index,
            chunk_index=r.chunk_index,
            score=hit.score,
        )
        for r, hit in rows
    ]



from typing import List
from app.rag.models import Chunk

class StructuredSearcher:
    def __init__(self, pg):
        self.pg = pg

    def search(self, filters: dict) -> List[Chunk]:
        rows = self.pg.fetch_chunks(filters)

        if not rows:
            return []

        chunks: List[Chunk] = []

        for r in rows:
            chunks.append(
                Chunk(
                    chunk_id=r["id"],
                    project=r["project"],
                    mpu_name=r["mpu_name"],
                    rg_index=r["rg_index"],
                    profile=r["profile"],
                    start_hex=r["start_hex"],
                    end_hex=r["end_hex"],
                    chunk_text=r["chunk_text"],
                    source="postgres"
                )
            )

        return chunks