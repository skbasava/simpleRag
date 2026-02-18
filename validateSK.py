# sk_orchestrator.py

from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function
from intent_engine import IntentEngine, registry
from typing import Dict, Any


# ==============================
# ROUTER PLUGIN
# ==============================

class RouterPlugin:

    def __init__(self, router):
        self.router = router

    @kernel_function(description="Route query to TAG, LLM or CLARIFY")
    def query_router(self, query: str) -> str:
        route = self.router.route(query)
        return route.type  # TAG / LLM


# ==============================
# ORCHESTRATOR
# ==============================

class SKOrchestrator:

    def __init__(self, router, policy_engine):
        self.kernel = Kernel()
        self.router_plugin = RouterPlugin(router)
        self.kernel.add_plugin(self.router_plugin, "router")

        self.intent_engine = IntentEngine(registry)
        self.policy_engine = policy_engine

    async def process(self, query: str, entities: Dict[str, Any]):

        # Step 1: Route
        route = await self.kernel.invoke(
            self.router_plugin.query_router,
            query=query
        )

        route = str(route)

        if route == "LLM":
            return {"type": "LLM"}

        # Step 2: Intent must already be extracted upstream
        intent = entities.get("intent")

        validation = self.intent_engine.validate(intent, entities)

        if not validation.valid:
            return {
                "type": "CLARIFY",
                "missing": validation.missing
            }

        # Step 3: Execute TAG
        result = self.policy_engine.execute(intent, entities)

        return {
            "type": "TAG",
            "result": result
        }