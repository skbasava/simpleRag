from typing import List
from app.rag.models import Chunk

class SemanticSearcher:
    def __init__(self, weaviate_client, embedder):
        self.wv = weaviate_client
        self.embedder = embedder

    def search(self, query: str, limit: int = 8) -> List[Chunk]:
        vector = self.embedder.embed(query)

        results = self.wv.semantic_search(vector, limit=limit)

        if not results:
            return []

        chunks: List[Chunk] = []

        for obj in results:
            props = obj["properties"]
            chunks.append(
                Chunk(
                    chunk_id=int(props["chunk_id"]),
                    project=props["project"],
                    mpu_name=props["mpu_name"],
                    rg_index=props["rg_index"],
                    profile=props["profile"],
                    start_hex=props["start"],
                    end_hex=props["end"],
                    chunk_text=props["chunk_text"],
                    source="weaviate",
                    score=obj.get("score")
                )
            )

        return chunks