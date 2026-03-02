"""Semantic Kernel service for IP Catalog query routing and execution."""

import logging
from typing import Any, Dict, List, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import ChatHistory
from semantic_kernel.functions import kernel_function

from backend.semantic.policy_plugin import PolicyPlugin
from backend.core.policy_engine import UnifiedPolicyEngine
from backend.services.query_router import QueryRouter

logger = logging.getLogger(__name__)

# Single source of truth for the registered service ID.
_SERVICE_ID = "qgenie-chat"

_DIRECT_LLM_SYSTEM_PROMPT = (
    "You are a helpful IP Catalog assistant. "
    "Provide clear explanations about XPU/NPU configurations, "
    "KG policies, and memory protection concepts."
)


# ---------------------------------------------------------------------------
# Plugin: DirectLLMPlugin
# ---------------------------------------------------------------------------

class DirectLLMPlugin:
    """
    Kernel plugin that routes simple queries directly to the LLM
    with function calling explicitly disabled.
    """

    def __init__(
        self,
        chat_completion: ChatCompletionClientBase,
        kernel: Kernel,
    ) -> None:
        self._chat_completion = chat_completion
        self._kernel = kernel

    @kernel_function(
        name="query_to_llm",
        description=(
            "STEP 3B (if ROUTE TO LLM): Send query directly to LLM for response. "
            "Used for simple questions, explanations, and general knowledge queries "
            "that don't require function calls or data lookups."
        ),
    )
    async def query_to_llm(
        self,
        query: str,
        chat_history: Optional[ChatHistory] = None,
    ) -> str:
        """
        Send a query directly to the LLM with function calling disabled.

        A local copy of chat_history is used — the caller's object is never mutated.
        Raises RuntimeError on failure so callers can handle errors structurally.
        """
        logger.info("[query_to_llm] Processing: %s", query)

        from backend.semantic.qgenie_connector import QGenieChatPromptExecutionSettings

        settings = QGenieChatPromptExecutionSettings(
            service_id=_SERVICE_ID,
            temperature=0.7,
            max_tokens=1500,
        )
        settings.function_choice_behavior = FunctionChoiceBehavior.NoneInvoke()

        # Build a local history — never mutate the caller's object.
        history = ChatHistory()
        if chat_history is not None:
            for msg in chat_history.messages:
                history.messages.append(msg)
        else:
            history.add_system_message(_DIRECT_LLM_SYSTEM_PROMPT)

        history.add_user_message(query)

        logger.info("[query_to_llm] Calling LLM (function calling disabled)")
        try:
            response = await self._chat_completion.get_chat_message_content(
                chat_history=history,
                settings=settings,
                kernel=self._kernel,
            )
        except Exception as e:
            logger.error("[query_to_llm] LLM call failed: %s", e, exc_info=True)
            raise RuntimeError(f"LLM call failed: {e}") from e

        logger.info("[query_to_llm] Response generated (%d chars)", len(str(response)))
        return str(response)


# ---------------------------------------------------------------------------
# Service: SemanticKernelService
# ---------------------------------------------------------------------------

class SemanticKernelService:
    """
    Orchestrates IP Catalog queries via Semantic Kernel.

    Plugins registered:
    - Router       : QueryRouter — decides ROUTE_TO_TAG vs ROUTE_TO_LLM
    - PolicySearch : PolicyPlugin — structured IP policy lookups
    - DirectLLM    : DirectLLMPlugin — fallback direct LLM path
    """

    def __init__(
        self,
        policy_engine: UnifiedPolicyEngine,
        model_provider: str = "qgenie",
        model_name: str = "Turbo",
        use_auto_function_calling: bool = True,
    ) -> None:
        self.policy_engine = policy_engine
        self.model_provider = model_provider
        self.model_name = model_name
        self.use_auto_function_calling = use_auto_function_calling

        # Build kernel and register the chat service first so plugins can
        # reference the service during their own init.
        self.kernel = Kernel()
        self._initialize_chat_service()

        # Retrieve the registered service for direct use.
        self.chat_completion: ChatCompletionClientBase = self.kernel.get_service(
            type=ChatCompletionClientBase
        )

        # Register plugins.
        self.query_router = QueryRouter(kernel=self.kernel)
        self.kernel.add_plugin(self.query_router, plugin_name="Router")

        self.policy_plugin = PolicyPlugin(policy_engine)
        self.kernel.add_plugin(self.policy_plugin, plugin_name="PolicySearch")

        self.direct_llm_plugin = DirectLLMPlugin(self.chat_completion, self.kernel)
        self.kernel.add_plugin(self.direct_llm_plugin, plugin_name="DirectLLM")

        logger.info(
            "SemanticKernelService initialized (provider: %s, model: %s, "
            "auto_function_calling: %s)",
            model_provider,
            model_name,
            use_auto_function_calling,
        )
        for plugin_name, plugin in self.kernel.plugins.items():
            for func in plugin:
                logger.debug("Registered kernel function: %s.%s", plugin_name, func.name)

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _initialize_chat_service(self) -> None:
        """Instantiate and register the chat completion service with the kernel."""
        if self.model_provider == "qgenie":
            import os
            from qgenie import QGenieClient
            from backend.semantic.qgenie_connector import QGenieChatCompletion

            api_key = os.environ.get("QGENIE_API_KEY")
            if not api_key:
                raise EnvironmentError(
                    "Environment variable QGENIE_API_KEY is not set."
                )

            qgenie_client = QGenieClient(api_key=api_key)
            chat_service = QGenieChatCompletion(
                service_id=_SERVICE_ID,
                ai_model_id=self.model_name,
                qgenie_client=qgenie_client,
            )
            self.kernel.add_service(chat_service)
            logger.info("QGenie chat service registered (model: %s)", self.model_name)
        else:
            raise ValueError(
                f"Unsupported model_provider: '{self.model_provider}'. "
                "Supported values: 'qgenie'."
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def execute_query(
        self,
        user_query: str,
        chat_history: Optional[ChatHistory] = None,
    ) -> Dict[str, Any]:
        """
        Execute a user query and return a flat, structured result dict.

        Args:
            user_query:    The raw query string from the user.
            chat_history:  Optional conversation history for multi-turn context.
                           Passed through to the inner execution but never mutated.

        Returns:
            {
                "query":            str,
                "response":         str | None,
                "functions_called": list[str],
                "success":          bool,
                "execution_method": str,
                "model_provider":   str,
                "metadata":         dict,
                "error":            str,   # only present on failure
            }
        """
        logger.info("Executing query: %s", user_query)

        try:
            if self.use_auto_function_calling:
                inner = await self._execute_with_auto_function_calling(
                    user_query, chat_history
                )
            else:
                response = await self.direct_llm_plugin.query_to_llm(
                    query=user_query,
                    chat_history=chat_history,
                )
                inner = {
                    "response": response,
                    "functions_called": [],
                    "metadata": {"success": True, "approach": "direct_llm"},
                }

            return {
                "query": user_query,
                "response": inner["response"],
                "functions_called": inner["functions_called"],
                "success": True,
                "execution_method": (
                    "auto_function_calling"
                    if self.use_auto_function_calling
                    else "direct_llm"
                ),
                "model_provider": self.model_provider,
                "metadata": inner["metadata"],
            }

        except Exception as e:
            logger.error("Query execution failed: %s", e, exc_info=True)
            return {
                "query": user_query,
                "response": None,
                "functions_called": [],
                "success": False,
                "execution_method": "unknown",
                "model_provider": self.model_provider,
                "error": str(e),
                "metadata": {"success": False},
            }

    # ------------------------------------------------------------------
    # Private execution strategies
    # ------------------------------------------------------------------

    async def _execute_with_auto_function_calling(
        self,
        user_query: str,
        chat_history: Optional[ChatHistory] = None,
    ) -> Dict[str, Any]:
        """
        Execute using Auto Function Calling.

        The LLM decides which plugins/functions to invoke and in what order,
        beginning with Router.route_query() as mandated by the system prompt.

        Returns a dict with keys: response, functions_called, metadata.
        """
        logger.info("Using Auto Function Calling")

        from backend.semantic.qgenie_connector import QGenieChatPromptExecutionSettings

        execution_settings = QGenieChatPromptExecutionSettings(
            service_id=_SERVICE_ID,
            tool_choice="auto",
        )
        execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto(
            filters={"included_plugins": ["Router", "PolicySearch", "DirectLLM"]}
        )

        # Build history — never mutate the caller's object.
        history = ChatHistory()
        history.add_system_message(self._create_system_message())
        if chat_history is not None:
            for msg in chat_history.messages:
                history.messages.append(msg)
        history.add_user_message(user_query)

        logger.info("Sending query to LLM with auto function calling enabled")
        result = await self.chat_completion.get_chat_message_content(
            chat_history=history,
            settings=execution_settings,
            kernel=self.kernel,
        )
        logger.info("Auto function calling completed")

        functions_called: List[str] = []
        if hasattr(result, "metadata") and result.metadata:
            raw_calls = result.metadata.get("function_calls", [])
            functions_called = [
                f"{call.get('plugin_name', 'unknown')}.{call.get('function_name', 'unknown')}"
                for call in raw_calls
            ]

        logger.info("Functions called: %s | Response: %d chars",
                    functions_called, len(str(result)))

        return {
            "response": str(result),
            "functions_called": functions_called,
            "metadata": {
                "success": True,
                "approach": "auto_function_calling",
                "function_count": len(functions_called),
            },
        }

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _create_system_message(self) -> str:
        """Build the system prompt for the LLM."""

        role_section = (
            "You are an IP Catalog Search Assistant.\n\n"

            "CRITICAL RULE: You MUST call functions using the full name format:\n"
            "PluginName.function_name(param1, param2, ...)\n"
            "Example: PolicySearch.get_mpu_summary(project=\"KAAMAPALLI\", "
            "mpu_name=\"XPU_G6F_pass_xpuA\", version=\"latest\")\n\n"
            "Never call a function without the plugin prefix.\n\n"

            "MANDATORY WORKFLOW — Follow these steps IN ORDER:\n"
            "1. ALWAYS call Router.route_query() FIRST\n"
            "   - Pass the user's query\n"
            "   - This returns a routing decision (ROUTE_TO_TAG or ROUTE_TO_LLM)\n\n"
            "2. If ROUTE_TO_TAG → call the matching PolicySearch function\n"
            "3. If ROUTE_TO_LLM → call DirectLLM.query_to_llm(query)\n\n"

            "CRITICAL RULES:\n"
            "- You MUST call Router.route_query() first — do NOT skip this step\n"
            "- Do NOT stop after Router.route_query(); always complete step 2 or 3\n\n"

            "Your role:\n"
            "- Answer questions about IP policies, MPU regions, and address mappings.\n"
            "- Always use the specific function that matches the query intent.\n"
            "- Never guess values — always call a function to retrieve real data.\n"
            "- If a required parameter is missing, ask the user for it.\n\n"
        )

        functions_section = (
            "Available Functions (always use full PluginName.function_name):\n\n"

            "Router:\n"
            "1. Router.route_query(query)\n"
            "   - Analyse the query and return ROUTE_TO_TAG or ROUTE_TO_LLM\n\n"

            "DirectLLM:\n"
            "2. DirectLLM.query_to_llm(query)\n"
            "   - Send query directly to LLM — used for general knowledge / explanations\n\n"

            "PolicySearch:\n"
            "3.  PolicySearch.count_resource_groups_per_mpu(project, version, mpu_name)\n"
            "    - Count RGs/regions within each MPU\n\n"
            "4.  PolicySearch.list_mpus(project, version, limit)\n"
            "    - List all MPUs for a project\n\n"
            "5.  PolicySearch.search_by_address(project, address, version, mpu_name)\n"
            "    - Find policies covering a memory address\n"
            "    - Use for: 'address 0x...', 'XPU for address', 'which MPU covers'\n\n"
            "6.  PolicySearch.search_by_region(project, region, version, mpu_name)\n"
            "    - Find policies for a region index\n\n"
            "7.  PolicySearch.get_regions_for_mpu(project, mpu_name, version, include_details)\n"
            "    - Get all regions defined in an MPU\n\n"
            "8.  PolicySearch.get_region_by_index(project, mpu_name, region_index, version)\n"
            "    - Get details for one specific region\n\n"
            "9.  PolicySearch.get_mpu_details(project, mpu_name, version)\n"
            "    - Get detailed information about a specific MPU/XPU\n\n"
            "10. PolicySearch.get_mpu_summary(project, mpu_name, version)\n"
            "    - Get summary of an MPU including region count and HSM config details\n\n"
            "11. PolicySearch.validate_access(project, address, region, version)\n"
            "    - Validate whether an address falls within a region\n\n"
        )

        decision_tree_section = (
            "--- FUNCTION SELECTION RULES (apply after ROUTE_TO_TAG) ---\n"
            "Apply the FIRST rule that matches. All calls MUST include the plugin prefix.\n\n"

            "IF query contains ('details for XPU' OR 'policy details' OR\n"
            "                   'show me the policy for' OR 'details for MPU' OR\n"
            "                   'information about XPU' OR 'summary for XPU')\n"
            "→ CALL: PolicySearch.get_mpu_summary(project, mpu_name, version)\n\n"

            "IF query contains ('regions in' OR 'RGs for' OR\n"
            "                   'show regions' OR 'list regions' OR 'all regions')\n"
            "→ CALL: PolicySearch.get_regions_for_mpu(project, mpu_name, version)\n\n"

            "IF query contains ('how many RGs' OR 'count' OR 'number of regions')\n"
            "→ CALL: PolicySearch.count_resource_groups_per_mpu(project, version, mpu_name)\n\n"

            "IF query contains a hex address like 0x...\n"
            "→ CALL: PolicySearch.search_by_address(project, address, version, mpu_name)\n\n"

            "IF query contains ('validate' OR 'is address in' OR 'check access')\n"
            "→ CALL: PolicySearch.validate_access(project, address, region, version)\n\n"

            "IF query contains ('list mpus' OR 'what mpus' OR 'show mpus')\n"
            "→ CALL: PolicySearch.list_mpus(project, version)\n\n"

            "IF NONE of the above match → call DirectLLM.query_to_llm(query).\n\n"
        )

        instructions_section = (
            "Formatting rules:\n"
            "- Always use the full PluginName.function_name form.\n"
            "- Break complex queries into sequential function calls.\n"
            "- Call functions in logical order (e.g. list MPUs first, then get regions).\n"
            "- Combine results into a single, clear, formatted response.\n"
            "- Be specific with numbers, addresses (hex), and region indices.\n"
            "- Format addresses as 0x{value:08X} (8-digit uppercase hex).\n\n"
        )

        examples_section = (
            "Example interactions:\n\n"

            "User: How many RGs does AOPSS_MPU_XPU4 have in KAANAPALI?\n"
            "Step 1 → Router.route_query(query=\"How many RGs...\")\n"
            "Step 2 → ROUTE_TO_TAG\n"
            "Step 3 → PolicySearch.count_resource_groups_per_mpu(\n"
            "          project=\"KAANAPALI\", version=None, mpu_name=\"AOPSS_MPU_XPU4\")\n"
            "Reply:   AOPSS_MPU_XPU4 has 12 resource groups in KAANAPALI.\n\n"

            "User: Show me details for XPU_CFG_LPASS_XPU4 in KAANAPALI\n"
            "Step 1 → Router.route_query(query=\"Show me details for...\")\n"
            "Step 2 → ROUTE_TO_TAG\n"
            "Step 3 → PolicySearch.get_mpu_details(\n"
            "          project=\"KAANAPALI\", mpu_name=\"XPU_CFG_LPASS_XPU4\", version=None)\n"
            "Reply:   Display MPU configuration details.\n\n"

            "User: Show regions for ANOC_IPA_MPU_XPU4 in project Hswl v3.5\n"
            "Step 1 → Router.route_query(query=\"Show regions for...\")\n"
            "Step 2 → ROUTE_TO_TAG\n"
            "Step 3 → PolicySearch.get_regions_for_mpu(\n"
            "          project=\"Hswl\", mpu_name=\"ANOC_IPA_MPU_XPU4\","
            " version=\"3.5\", include_details=True)\n"
            "Reply:   List each region with index, start address, end address.\n\n"

            "User: What is an MPU?\n"
            "Step 1 → Router.route_query(query=\"What is an MPU?\")\n"
            "Step 2 → ROUTE_TO_LLM\n"
            "Step 3 → DirectLLM.query_to_llm(query=\"What is an MPU?\")\n"
            "Reply:   An MPU (Memory Protection Unit) is...\n"
        )

        return (
            role_section
            + functions_section
            + decision_tree_section
            + instructions_section
            + examples_section
        )
