from rag.session import RAGSession
from rag.context_resolver import resolve_context
from rag.router import route_query
from rag.prompt_builder import build_prompt
from llm.async_client import submit_prompt_async

class AsyncRAGService:
    def __init__(self):
        self.session = RAGSession()

    async def answer(self, user_query: str) -> str:
        project, version, clarification = resolve_context(
            user_query, self.session
        )

        if clarification:
            return clarification

        self.session.project = project
        self.session.version = version

        route = route_query(user_query)

        context = await route.retrieve_async(
            query=user_query,
            project=project,
            version=version
        )

        prompt = build_prompt(
            user_query=user_query,
            context=context,
            project=project,
            version=version
        )

        return await submit_prompt_async(prompt)
