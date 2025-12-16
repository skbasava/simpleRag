import re
from dataclasses import dataclass
from typing import Optional, Dict


# ---------------------------
# Output contract
# ---------------------------

@dataclass(frozen=True)
class ContextResult:
    project: Optional[str]
    version: Optional[str]
    mpu: Optional[str]
    profile: Optional[str]
    clarification: Optional[str]


# ---------------------------
# Resolver
# ---------------------------

class ContextResolver:
    """
    Extracts required context from user query.
    Never raises.
    Never queries DB.
    """

    PROJECT_RE = re.compile(r"\b([A-Z][A-Z0-9_-]{2,})\b")
    VERSION_RE = re.compile(r"\b(v|version)\s*([0-9]+(?:\.[0-9]+)*)\b", re.I)
    MPU_RE = re.compile(r"\bMPU[_\-\w]+\b", re.I)
    PROFILE_RE = re.compile(r"\b(MSA|TZ|TME_FW|TME_ROM)\b", re.I)

    def resolve(
        self,
        query: str,
        prior_context: Optional[Dict[str, str]] = None,
    ) -> ContextResult:
        """
        Resolve context from user query.
        prior_context may contain project/version from earlier turn.
        """

        prior_context = prior_context or {}

        project = self._extract_project(query) or prior_context.get("project")
        version = self._extract_version(query) or prior_context.get("version")
        mpu = self._extract_mpu(query)
        profile = self._extract_profile(query)

        # Decide clarification
        clarification = self._clarify(project, version)

        return ContextResult(
            project=project,
            version=version,
            mpu=mpu,
            profile=profile,
            clarification=clarification,
        )

    # ---------------------------
    # Extraction helpers
    # ---------------------------

    def _extract_project(self, query: str) -> Optional[str]:
        matches = self.PROJECT_RE.findall(query)
        if not matches:
            return None

        # Heuristic: longest uppercase token is project
        return max(matches, key=len)

    def _extract_version(self, query: str) -> Optional[str]:
        match = self.VERSION_RE.search(query)
        return match.group(2) if match else None

    def _extract_mpu(self, query: str) -> Optional[str]:
        match = self.MPU_RE.search(query)
        return match.group(0) if match else None

    def _extract_profile(self, query: str) -> Optional[str]:
        match = self.PROFILE_RE.search(query)
        return match.group(1).upper() if match else None

    # ---------------------------
    # Clarification logic
    # ---------------------------

    def _clarify(
        self,
        project: Optional[str],
        version: Optional[str],
    ) -> Optional[str]:

        if not project and not version:
            return "Please specify the project name and policy version."

        if not project:
            return "Please specify the project name."

        if not version:
            return f"Please specify the policy version for project {project}."

        return None