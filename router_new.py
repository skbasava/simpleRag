from app.rag.structured_search import StructuredSearcher
from app.rag.semantic_search import SemanticSearcher
from app.rag.chunk_merger import ChunkMerger

class RAGRouter:
    def __init__(self, pg, weaviate, embedder):
        self.structured = StructuredSearcher(pg)
        self.semantic = SemanticSearcher(weaviate, embedder)

    def retrieve_chunks(self, query: str, filters: dict):
        structured_chunks = self.structured.search(filters)
        semantic_chunks = self.semantic.search(query)

        return ChunkMerger.merge(structured_chunks, semantic_chunks)