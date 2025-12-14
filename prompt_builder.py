import json
from typing import List, Dict

# -------------------------------------------------------------
# SYSTEM PROMPT (STATIC)
# -------------------------------------------------------------
SYSTEM_PROMPT = """
You are an expert MPU/PRtn access-policy analysis assistant.
You MUST answer ONLY using the provided CONTEXT.
Never guess or fabricate MPU names, address ranges, or policies.
Base all explanations strictly on the XML-derived chunk metadata.
"""


# -------------------------------------------------------------
# FORMAT A SINGLE CONTEXT CHUNK INTO CLEAN TEXT
# -------------------------------------------------------------
def format_chunk(c: Dict) -> str:
    """
    Convert a single DB/vector object row into human-readable text.
    Works for Postgres rows & Weaviate objects.
    """

    # For Postgres rows (tuple form)
    if isinstance(c, tuple):
        project, mpu_name, rg_index, profile, start_hex, end_hex, chunk_xml = c
        return f"""
Project: {project}
MPU: {mpu_name}
Region Index (RG): {rg_index}
Profile: {profile}
Start: {start_hex}
End: {end_hex}

Raw XML:
{chunk_xml}
"""

    # For Weaviate JSON-like object
    if isinstance(c, dict):
        return f"""
Project: {c.get('project')}
MPU: {c.get('mpu_name')}
Region Index: {c.get('rg_index')}
Profile: {c.get('profile')}

Raw XML:
{c.get('chunk_text')}
"""

    return ""


# -------------------------------------------------------------
# BUILD CONTEXT BLOCK FROM MULTIPLE CHUNKS
# -------------------------------------------------------------
def build_context_block(chunks: List[Dict]) -> str:
    if not chunks:
        return "NO CONTEXT FOUND"

    ctx = "\n".join(format_chunk(c) for c in chunks[:20])  # limit to 20 chunks max
    return ctx


# -------------------------------------------------------------
# BUILD FINAL PROMPT FOR LLM
# -------------------------------------------------------------
def build_final_prompt(user_query: str, context_chunks: List[Dict]) -> str:
    """
    Creates the final prompt sent to the LLM.
    Includes:
      - System prompt
      - RAG context
      - User question
    """

    context_text = build_context_block(context_chunks)

    prompt = f"""
SYSTEM:
{SYSTEM_PROMPT}

CONTEXT:
{context_text}

USER QUESTION:
{user_query}

INSTRUCTIONS:
- Use the context to answer the question.
- If context seems incomplete, say: "No matching policy context found".
- Do not invent MPU names, addresses, or values not present in context.
- If analyzing differences, reference the chunk_text or metadata.
"""

    return prompt.strip()
