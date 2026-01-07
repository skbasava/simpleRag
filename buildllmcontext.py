def _build_llm_context(
    self,
    user_query: str,
    hyde_text: str,
    execution_result: Dict,
    facts: QueryFacts,
) -> str:
    rows = execution_result.get("rows", [])
    entity = facts.entity

    renderer = RENDERERS.get(entity)
    if not renderer:
        raise ValueError(f"No renderer registered for entity {entity}")

    header = renderer.header(rows)
    body = renderer.render_rows(rows)
    explanation = renderer.explain()

    context = f"""
You are answering a structured database query.

User question:
{user_query}

Query intent:
- Intent: {facts.intent.name}
- Operation: {facts.operation.name}
- Entity: {facts.entity.name}

Database result summary:
{header}

Sample records:
{body if body else "(no records)"}

Guidelines:
- Do NOT list all records.
- Provide a concise summary.
- Mention total counts.
- Highlight patterns if applicable.

Explainability:
{explanation}
"""

    return context.strip()