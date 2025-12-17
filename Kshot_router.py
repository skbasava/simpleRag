class RAGRouter:
    def __init__(self, pg, weaviate, embedder, kshot):
        self.pg = pg
        self.wv = weaviate
        self.embedder = embedder
        self.kshot = kshot

        self.structured = StructuredSearcher(pg)
        self.semantic = SemanticSearcher(weaviate, embedder)

    def retrieve_chunks(self, query: str, filters: dict):
        rewritten = self.kshot.rewrite(
            query,
            filters.get("project"),
            filters.get("version"),
        )

        structured_chunks = self.structured.search(filters)
        semantic_chunks = self.semantic.search(rewritten)

        return ChunkMerger.merge(structured_chunks, semantic_chunks)