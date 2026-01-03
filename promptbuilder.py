


from kshot_loader import load_kshot_examples
from kshot_renderer import render_kshots
from sql_context import build_sql_context


import yaml
from typing import List, Dict


def load_kshot_examples(path: str) -> str:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    blocks = []
    for ex in data.get("examples", []):
        blocks.append(
            f"### Example\n"
            f"User: {ex['user']}\n"
            f"Answer: {ex['assistant']}\n"
        )
    return "\n".join(blocks)


def build_sql_context(sql_rows: List[Dict]) -> str:
    if not sql_rows:
        return "No matching policy entries found."

    lines = []
    for r in sql_rows:
        lines.append(
            f"- Project: {r['project']}, Version: {r['version']}\n"
            f"  MPU: {r['mpu_name']} (Region {r['rg_index']})\n"
            f"  Address Range: {r['addr_start']} - {r['addr_end']}\n"
            f"  Covers Address: {r.get('covers_address', 'unknown')}\n"
        )
    return "\n".join(lines)


def build_final_prompt(
    user_query: str,
    hyde_text: str,
    sql_rows: List[Dict],
    kshot_yaml_path: str,
) -> str:
    kshot_block = load_kshot_examples(kshot_yaml_path)
    sql_context = build_sql_context(sql_rows)

    return f"""
You are a security policy analysis assistant.
Answer strictly using the provided context.
Do not hallucinate MPU names, address ranges, or projects.

{f"K-SHOT EXAMPLES:\n{kshot_block}" if kshot_block else ""}

CONTEXT (Authoritative Data):
{sql_context}

HyDE Interpretation:
{hyde_text}

USER QUESTION:
{user_query}

Provide a precise, technically accurate answer.
""".strip()



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