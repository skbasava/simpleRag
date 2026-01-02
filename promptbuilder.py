from kshot_loader import load_kshot_examples
from kshot_renderer import render_kshots
from sql_context import build_sql_context

def build_final_prompt(
    *,
    user_query: str,
    hyde_text: str,
    sql_rows: list[dict],
    kshot_yaml_path: str,
    vector_context: str | None = None,
) -> str:
    system_prompt = """
You are an MPU policy analysis assistant.

Rules:
- Use ONLY the provided SQL Context for factual claims.
- Never invent MPU regions, addresses, or permissions.
- If required information is missing, ask a clarification question.
- Always explain WHY a region was chosen.
"""

    kshots = load_kshot_examples(kshot_yaml_path, max_examples=3)
    kshot_block = render_kshots(kshots)
    sql_context = build_sql_context(sql_rows)

    vector_block = (
        f"\nOptional Documentation Context:\n{vector_context}"
        if vector_context else ""
    )

    instructions = """
Instructions:
1. Identify matching MPU region(s) from SQL Context.
2. Explain region choice using address coverage, region size, and priority.
3. If SQL Context is empty, ask for missing inputs.
4. Do NOT assume defaults unless explicitly stated.
"""

    prompt = f"""
SYSTEM:
{system_prompt}

{ kshot_block }

CURRENT SQL CONTEXT:
{ sql_context }

{ vector_block }

USER QUERY:
{ user_query }

HyDE INTENT:
{ hyde_text }

{ instructions }
""".strip()

    return prompt