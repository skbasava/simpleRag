"""
Fixed: _handle_qgenie_function_call
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Screenshot line-by-line review — all 8 bugs found and fixed:

  BUG 1 — re.search(r'to=functions\.(\w+)')
    \w+ stops at "." so "PolicySearch.get_mpu_summary" → captured as "PolicySearch" only.
    Wrong function name passed to everything downstream.
    FIX: r'to=functions\.([\w.]+)' + split on "." → plugin_name + function_name.

  BUG 2 — self._function_exists(kernel, function_name)
    function_name = "PolicySearch" (just the plugin, from Bug 1).
    kernel.plugins["PolicySearch"] EXISTS so check always returned True.
    Wrong function executed silently.
    FIX: _function_exists(kernel, plugin_name, function_name) checks both.

  BUG 3 — messages.append({"role": "user", "content": "Function returned..."})
    QGenie sees role="user" as a NEW user turn → re-triggers the same tool call.
    Causes infinite loop: result → re-read → call same tool → repeat.
    FIX: role="tool" + tool_call_id so QGenie knows this is a tool response.

  BUG 4 — while loop with no early exit on clean response
    After getting clean text the loop continues all 5 iterations.
    FIX: explicit return inside the "no function call detected" branch.

  BUG 5 — if len(cleaned_content) < 50 or not any(word in ... ['region','found',...])
    Hardcoded word list discards valid short answers like "No policies configured."
    FIX: only fallback when response is genuinely empty or metadata-only.

  BUG 6 — r'<\|message\|>(.*?)<\|call\|>' with re.DOTALL
    Captures trailing whitespace/newlines after JSON closing brace.
    json.loads() fails on trailing content.
    FIX: brace-depth counter extracts exact JSON object.

  BUG 7 — import re inside the while loop (visible in screenshot)
    Re-importing on every iteration — wasteful and confusing.
    FIX: all imports at top of module, regex patterns compiled once.

  BUG 8 — str(response) fallback on unknown response type
    Produces "<QGenieResponse object at 0x...>" — not usable.
    FIX: try all known QGenie response shapes before str() fallback.
"""

# ── All imports at top level — NOT inside loops (BUG 7 FIX) ─────────────────
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

logger = logging.getLogger(__name__)

PLUGIN_NAME = "PolicySearch"   # must match kernel.add_plugin(..., plugin_name=...)

# ── Regex patterns compiled ONCE at module load — not inside loops ───────────
# BUG 7 FIX: original code had "import re" inside the while/try block
_FN_CALL_RE  = re.compile(r'to=functions\.([\w.]+)')            # BUG 1 FIX: [\w.]+ not \w+
_MESSAGE_RE  = re.compile(r'<\|message\|>(.*?)<\|call\|>', re.DOTALL)
_TOKEN_STRIP = re.compile(r'<\|[^|]+\|>')


# ─────────────────────────────────────────────────────────────────────────────
# HELPER 1 — extract JSON by brace depth (BUG 6 FIX)
# ─────────────────────────────────────────────────────────────────────────────
def _extract_json_by_braces(text: str) -> Optional[str]:
    """
    Extract the first complete JSON object by counting { } depth.
    BUG 6 FIX: regex (.*?) with re.DOTALL captured trailing junk after '}'.
    This method stops exactly at the matching closing brace.
    """
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return text[start : i + 1]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# HELPER 2 — parse QGenie function call token (BUG 1 FIX)
# ─────────────────────────────────────────────────────────────────────────────
def _parse_qgenie_function_call(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse QGenie <|token|> format into structured dict.

    BUG 1 FIX: old regex r'to=functions\.(\w+)' stopped at '.' so:
      "to=functions.PolicySearch.get_mpu_summary"
      captured group(1) = "PolicySearch"   ← WRONG (just the plugin)

    New regex r'to=functions\.([\w.]+)' captures:
      group(1) = "PolicySearch.get_mpu_summary"   ← CORRECT

    Returns:
      {
        "plugin_name":   "PolicySearch",
        "function_name": "get_mpu_summary",
        "full_name":     "PolicySearch.get_mpu_summary",
        "arguments":     {"project": "KAANAPALI", ...},
        "tool_call_id":  "uuid..."
      }
    """
    fn_match = _FN_CALL_RE.search(content)
    if not fn_match:
        return None

    raw_name = fn_match.group(1).strip()

    # Split "PolicySearch.get_mpu_summary" → plugin + function
    if "." in raw_name:
        plugin_name, function_name = raw_name.split(".", 1)
    else:
        # Bare name — attach known default plugin
        plugin_name   = PLUGIN_NAME
        function_name = raw_name

    full_name = f"{plugin_name}.{function_name}"

    # Extract <|message|>{...}<|call|> block
    msg_match = _MESSAGE_RE.search(content)
    if not msg_match:
        logger.warning(
            "Function call token found (%s) but no <|message|>...<|call|> block",
            full_name,
        )
        return None

    raw_json = msg_match.group(1).strip()

    # BUG 6 FIX: extract JSON by brace depth, not raw regex group
    json_str = _extract_json_by_braces(raw_json) or raw_json
    try:
        arguments = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(
            "JSON parse failed for '%s' args='%s': %s",
            full_name, json_str[:120], e,
        )
        arguments = {}

    tool_call_id = f"{plugin_name}.{function_name}.{uuid.uuid4().hex[:8]}"

    logger.info(
        "Parsed: raw='%s' → plugin='%s'  fn='%s'  args=%s",
        raw_name, plugin_name, function_name, arguments,
    )

    return {
        "plugin_name":   plugin_name,
        "function_name": function_name,
        "full_name":     full_name,
        "arguments":     arguments,
        "tool_call_id":  tool_call_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HELPER 3 — response content extraction (BUG 8 FIX)
# ─────────────────────────────────────────────────────────────────────────────
def _extract_content(response: Any) -> str:
    """
    Safely extract string content from any QGenie response shape.

    BUG 8 FIX: original code fell back to str(response) which produces
    "<QGenieResponse object at 0x7f...>" — completely unusable as content.
    Now tries all known shapes before a last-resort fallback.
    """
    # Shape 1: OpenAI-style .choices[0].message.content
    if hasattr(response, "choices") and response.choices:
        msg = response.choices[0].message
        return getattr(msg, "content", "") or ""

    # Shape 2: dict with content / text / message.content
    if isinstance(response, dict):
        return (
            response.get("content")
            or response.get("text")
            or (response.get("message") or {}).get("content", "")
            or ""
        )

    # Shape 3: object with .content or .text attribute
    for attr in ("content", "text"):
        val = getattr(response, attr, None)
        if val and isinstance(val, str):
            return val

    # Shape 4: plain string
    if isinstance(response, str):
        return response

    # Last resort — log a warning so it's visible in logs
    logger.warning(
        "Unknown QGenie response type: %s — could not extract content",
        type(response).__name__,
    )
    return ""


def _is_function_call_response(content: str) -> bool:
    """Return True if content contains a QGenie tool call token."""
    return bool(_FN_CALL_RE.search(content))


def _clean_response(content: str) -> str:
    """Strip all <|token|> markers and collapse whitespace."""
    return _TOKEN_STRIP.sub("", content).strip()


def _is_empty_or_metadata_only(content: str) -> bool:
    """
    BUG 5 FIX: old code checked len < 50 AND word list → discarded valid
    short answers like "No policies configured for this MPU." (41 chars).
    Only return True when content is genuinely empty after stripping tokens.
    """
    return len(_TOKEN_STRIP.sub("", content).strip()) == 0


# ─────────────────────────────────────────────────────────────────────────────
# MAIN METHOD
# ─────────────────────────────────────────────────────────────────────────────
    async def _handle_qgenie_function_call(
        self,
        content: str,
        chat_history: "ChatHistory",
        settings: "PromptExecutionSettings",
        kernel: Any,
        messages: List[Dict],
        max_iterations: int = 5,
    ) -> ChatMessageContent:
        """
        Handle QGenie's custom function call format with multiple iterations.

        Per-iteration flow:
          1.  Detect tool call token in current_content
          2.  Parse plugin_name + function_name + arguments         (BUG 1 FIX)
          3.  Verify function exists in kernel with BOTH names      (BUG 2 FIX)
          4.  Execute via kernel.invoke(plugin_name, function_name)
          5.  Append result as role="tool" NOT role="user"          (BUG 3 FIX)
          6.  Call QGenie to summarise
          7.  If clean response → return immediately                (BUG 4 FIX)
          8.  Otherwise loop

        BUG 7 FIX: "import re" has been moved to top of module (was in this loop).
        """
        iteration       = 0
        current_content = content

        while iteration < max_iterations:
            iteration += 1
            logger.info("Function call iteration %d/%d", iteration, max_iterations)

            # ── Step 1: Check for function call token ─────────────────────────
            if not _is_function_call_response(current_content):
                cleaned = _clean_response(current_content)
                logger.info(
                    "No function call detected — returning final response (%d chars)",
                    len(cleaned),
                )

                # BUG 5 FIX: only fallback if truly empty, not just short
                if _is_empty_or_metadata_only(current_content):
                    logger.warning("Empty/metadata-only response → summary fallback")
                    return self._create_summary_from_messages(messages)

                # BUG 4 FIX: explicit early return (original continued the loop)
                return ChatMessageContent(
                    role=AuthorRole.ASSISTANT,
                    content=cleaned,
                )

            try:
                # ── Step 2: Parse function call ───────────────────────────────
                # BUG 1 FIX: new parser captures "PolicySearch.get_mpu_summary"
                # old regex captured only "PolicySearch"
                parsed = _parse_qgenie_function_call(current_content)
                if not parsed:
                    logger.warning("Could not parse function call — summary fallback")
                    return self._create_summary_from_messages(messages)

                plugin_name   = parsed["plugin_name"]
                function_name = parsed["function_name"]
                full_name     = parsed["full_name"]
                function_args = parsed["arguments"]
                tool_call_id  = parsed["tool_call_id"]

                logger.info(
                    "Executing: plugin='%s'  function='%s'  args=%s",
                    plugin_name, function_name, function_args,
                )

                # ── Step 3: Verify function exists ────────────────────────────
                # BUG 2 FIX: old code passed just function_name="PolicySearch"
                # (the plugin name from bug 1) — check always passed silently.
                # Now checks kernel.plugins[plugin_name].functions[function_name].
                if not self._function_exists(kernel, plugin_name, function_name):
                    logger.warning(
                        "Function not found in kernel: %s", full_name
                    )
                    return self._create_summary_from_messages(messages)

                # ── Step 4: Execute ───────────────────────────────────────────
                result = await self._execute_function(
                    kernel, plugin_name, function_name, function_args
                )
                logger.info(
                    "Executed %s → result %d chars", full_name, len(str(result))
                )

                # ── Step 5: Append as role="tool" ─────────────────────────────
                # BUG 3 FIX: was role="user" → QGenie re-triggered the tool call
                # on the next iteration creating an infinite loop.
                # role="tool" with matching tool_call_id tells QGenie this is
                # the result of a function call, not a new user request.
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call_id,
                    "name":         full_name,
                    "content":      str(result),
                })

                # Separate assistant message asking QGenie to summarise
                messages.append({
                    "role":    "user",
                    "content": (
                        f"The function {full_name} returned the above result. "
                        "Please provide a clear, concise natural language summary."
                    ),
                })

                logger.info(
                    "Calling QGenie to summarise (iteration %d)", iteration
                )

                # ── Step 6: Call QGenie for summary ───────────────────────────
                response = await self.qgenie_client.chat(messages=messages)

                # BUG 8 FIX: safe content extraction (was: str(response) fallback)
                current_content = _extract_content(response)
                logger.info("New response: %d chars", len(current_content))

            except json.JSONDecodeError as e:
                logger.error("JSON parse error: %s", e)
                return self._create_summary_from_messages(messages)

            except Exception as e:
                logger.error("Iteration %d failed: %s", iteration, e, exc_info=True)
                return self._create_summary_from_messages(messages)

        # ── Max iterations reached ────────────────────────────────────────────
        logger.warning("Max iterations (%d) reached", max_iterations)
        return self._create_summary_from_messages(messages)


# ─────────────────────────────────────────────────────────────────────────────
# _function_exists — BUG 2 FIX
# ─────────────────────────────────────────────────────────────────────────────
    def _function_exists(
        self,
        kernel: Any,
        plugin_name: str,
        function_name: str,
    ) -> bool:
        """
        Verify both plugin AND function exist in the kernel.

        BUG 2 FIX: old signature _function_exists(kernel, function_name)
        received function_name="PolicySearch" (from bug 1 wrong parse).
        kernel.plugins.get("PolicySearch") returned the plugin object (not None)
        so the check always passed — any function name was "found".
        """
        try:
            plugin = kernel.plugins.get(plugin_name)
            if not plugin:
                logger.warning(
                    "Plugin '%s' not registered. Registered plugins: %s",
                    plugin_name,
                    list(kernel.plugins.keys()) if hasattr(kernel, "plugins") else "N/A",
                )
                return False

            fn = plugin.functions.get(function_name)
            if not fn:
                logger.warning(
                    "Function '%s' not in plugin '%s'. Available: %s",
                    function_name,
                    plugin_name,
                    list(plugin.functions.keys()),
                )
                return False

            return True

        except Exception as e:
            logger.error("_function_exists check error: %s", e)
            return False


# ─────────────────────────────────────────────────────────────────────────────
# _execute_function
# ─────────────────────────────────────────────────────────────────────────────
    async def _execute_function(
        self,
        kernel: Any,
        plugin_name: str,
        function_name: str,
        function_args: Dict[str, Any],
    ) -> str:
        """Execute kernel function. Always returns a string."""
        result = await kernel.invoke(
            plugin_name=plugin_name,
            function_name=function_name,
            **function_args,
        )
        return str(result) if result is not None else ""


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS — run standalone: python _handle_qgenie_function_call.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    passed = failed = 0

    def check(name, actual, expected):
        global passed, failed
        if actual == expected:
            print(f"  ✅ {name}")
            passed += 1
        else:
            print(f"  ❌ {name}")
            print(f"     expected: {expected!r}")
            print(f"     got     : {actual!r}")
            failed += 1

    # ── BUG 1: regex captures full prefixed name ──────────────────────────────
    print("\nBUG 1 — Regex captures plugin.function correctly")
    cases = [
        (
            "<|start|>assistant<|channel|>commentary "
            "to=functions.PolicySearch.get_mpu_summary "
            "<|constrain|>json<|message|>"
            '{"project":"KAANAPALI","mpu_name":"XPU_cfg_Lpass_xpu4","version":"latest"}'
            "<|call|>",
            "PolicySearch", "get_mpu_summary",
            {"project": "KAANAPALI", "mpu_name": "XPU_cfg_Lpass_xpu4", "version": "latest"},
        ),
        (
            "to=functions.get_regions_for_mpu <|message|>"
            '{"project":"WAIPIO","mpu_name":"AOPSS_MPU_XPU4"}<|call|>',
            PLUGIN_NAME, "get_regions_for_mpu",
            {"project": "WAIPIO", "mpu_name": "AOPSS_MPU_XPU4"},
        ),
    ]
    for content, exp_plugin, exp_fn, exp_args in cases:
        r = _parse_qgenie_function_call(content)
        assert r, f"Failed to parse: {content[:60]}"
        check(f"plugin_name={exp_plugin}", r["plugin_name"], exp_plugin)
        check(f"function_name={exp_fn}", r["function_name"], exp_fn)
        check(f"arguments", r["arguments"], exp_args)

    # ── BUG 5: short valid answers not discarded ──────────────────────────────
    print("\nBUG 5 — Short valid answers not discarded")
    check("'No policies configured.' is NOT empty",
          _is_empty_or_metadata_only("No policies configured."), False)
    check("'Found 0 regions.' is NOT empty",
          _is_empty_or_metadata_only("Found 0 regions."), False)
    check("'' IS empty",
          _is_empty_or_metadata_only(""), True)
    check("Only tokens IS empty",
          _is_empty_or_metadata_only("<|start|><|end|>"), True)

    # ── BUG 6: brace-depth JSON extraction ───────────────────────────────────
    print("\nBUG 6 — Brace-depth JSON extraction")
    text = '{"project":"KAANAPALI","nested":{"key":"val"}}\nextra junk'
    result = _extract_json_by_braces(text)
    check("Extracts exact JSON, no trailing junk",
          result, '{"project":"KAANAPALI","nested":{"key":"val"}}')

    # ── BUG 8: response content extraction ───────────────────────────────────
    print("\nBUG 8 — Response content extraction")

    class MockChoices:
        class message:
            content = "Policy details for KAANAPALI"
        choices = [type("C", (), {"message": message})]

    check("OpenAI-style .choices",
          _extract_content(MockChoices()), "Policy details for KAANAPALI")
    check("Dict content key",
          _extract_content({"content": "hello"}), "hello")
    check("Dict text key",
          _extract_content({"text": "world"}), "world")
    check("Plain string",
          _extract_content("direct string"), "direct string")

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
