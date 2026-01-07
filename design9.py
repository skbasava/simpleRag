# rag/renderers/base.py
from abc import ABC, abstractmethod
from typing import List, Dict

class EntityRenderer(ABC):
    @abstractmethod
    def header(self, rows: List[Dict]) -> str:
        pass

    @abstractmethod
    def render_rows(self, rows: List[Dict]) -> str:
        pass

    @abstractmethod
    def explain(self) -> str:
        pass


# rag/renderers/policy.py
from .base import EntityRenderer

class PolicyRenderer(EntityRenderer):
    def header(self, rows):
        return f"Total MPU policies found: {len(rows)}"

    def render_rows(self, rows):
        return "\n".join(
            f"- {r['mpu_name']} "
            f"[{hex(r['addr_start'])} - {hex(r['addr_end'])}]"
            for r in rows[:10]
        )

    def explain(self):
        return "List of MPU access policies"
        

# rag/renderers/project.py
from .base import EntityRenderer

class ProjectRenderer(EntityRenderer):
    def header(self, rows):
        return f"Total projects found: {len(rows)}"

    def render_rows(self, rows):
        return "\n".join(
            f"- {r['project']} "
            f"(version={r.get('version')}, latest={r.get('is_latest')})"
            for r in rows[:10]
        )

    def explain(self):
        return "List of supported projects"


# rag/renderers/version.py
from .base import EntityRenderer

class VersionRenderer(EntityRenderer):
    def header(self, rows):
        return f"Total versions found: {len(rows)}"

    def render_rows(self, rows):
        return "\n".join(
            f"- Project {r['project']} → Version {r['version']}"
            for r in rows[:10]
        )

    def explain(self):
        return "List of supported project versions"


# rag/renderers/address.py
from .base import EntityRenderer

class AddressRenderer(EntityRenderer):
    def header(self, rows):
        return f"MPU policies covering this address: {len(rows)}"

    def render_rows(self, rows):
        return "\n".join(
            f"- {r['mpu_name']} "
            f"[{hex(r['addr_start'])} - {hex(r['addr_end'])}]"
            for r in rows[:10]
        )

    def explain(self):
        return "MPU policies matching the given address"

# rag/renderers/registry.py
from rag.query_helpers.queryfacts import Entity
from .policy import PolicyRenderer
from .project import ProjectRenderer
from .version import VersionRenderer
from .address import AddressRenderer

RENDERERS = {
    Entity.POLICY: PolicyRenderer(),
    Entity.PROJECT: ProjectRenderer(),
    Entity.VERSION: VersionRenderer(),
    Entity.ADDRESS: AddressRenderer(),
}


