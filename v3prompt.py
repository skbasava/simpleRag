def _build_llm_context_v2(
    self,
    user_query: str,
    hyde_text: str,
    execution_result: Dict,
    facts: QueryFacts,
) -> str:
    """
    Build LLM context for both:
    - Structured TAG results (rows)
    - Unstructured policy results (raw_text)
    """

    # ✅ CASE 1: Raw text based execution (policy-by-address / region)
    if execution_result.get("text"):
        confidence = execution_result.get("confidence")
        explainability = execution_result.get("explainability")

        return f"""
You are a domain-specific RAG assistant.

User question:
{user_query}

Retrieved policy text (authoritative source):
{execution_result['text']}

Guidelines:
- Do NOT hallucinate addresses, registers, or ranges.
- Summarize clearly and accurately.
- If confidence or explainability is missing, omit it gracefully.
"""

    # ------------------------------------------------------
    # ✅ CASE 2: Structured TAG execution (existing logic)
    # ------------------------------------------------------

    rows = execution_result.get("rows", [])
    entities = facts.entity or []
    entity = entities[0] if entities else None

    renderer = RENDERS.get(entity)
    if not renderer:
        raise ValueError(f"No renderer registered for entity {entity}")

    header = renderer.header(rows)
    body = renderer.render_rows(rows)
    explanation = renderer.explain()

    entity_names = ", ".join(e.name for e in entities) if entities else "UNKNOWN"

    return f"""
You are answering a structured database query.

User question:
{user_query}

Query intent:
- Intent: {facts.intent.name}
- Operation: {facts.operation.name}
- Entity: {entity_names}

Database result summary:
{header}

Details:
{body}

Explanation:
{explanation}
"""