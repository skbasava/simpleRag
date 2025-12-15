import re
from typing import Tuple, Optional

PROJECTS = {"KAANAPALI", "MAUI", "OAHU", "BIGISLAND"}

def resolve_context(
    query: str,
    session
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Returns: (project, version, clarification_question)
    """

    project = session.project or extract_project(query)
    version = session.version or extract_version(query)

    if not project and not version:
        return None, None, (
            "Please specify:\n"
            "• Project name (e.g., KAANAPALI)\n"
            "• Policy XML version (e.g., 5.3)"
        )

    if not project:
        return None, None, "Please specify the project name."

    if not version:
        return None, None, (
            f"Please specify the policy XML version for project {project}."
        )

    return project, version, None


def extract_project(query: str) -> Optional[str]:
    for p in PROJECTS:
        if p.lower() in query.lower():
            return p
    return None


def extract_version(query: str) -> Optional[str]:
    m = re.search(r"\b(v?\d+\.\d+)\b", query)
    return m.group(1).lstrip("v") if m else None
