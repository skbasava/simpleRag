class RAGService:
    def __init__(self, router, context_resolver):
        self.router = router
        self.context = context_resolver

    async def answer(self, query: str) -> dict:
        project, version, clarification = self.context.resolve(query)

        if clarification:
            return {
                "answer": clarification,
                "needs_context": True
            }

        filters = {
            "project": project,
            "version": version
        }

        chunks = self.router.retrieve_chunks(query, filters)

        if not chunks:
            return {
                "answer": "No matching policy found.",
                "needs_context": False
            }

        context_text = "\n".join(c.chunk_text for c in chunks[:6])

        return {
            "answer": context_text,
            "needs_context": False
        }