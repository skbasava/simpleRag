# intent_engine.py

from enum import Enum, auto
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

# ==============================
# DOMAIN DEFINITIONS
# ==============================

class Domain(Enum):
    POLICY = auto()
    HARDWARE = auto()
    REGISTER = auto()
    SUMMARY = auto()
    ADDRESS = auto()
    VALIDATION = auto()


# ==============================
# INTENT META STRUCTURE
# ==============================

@dataclass
class IntentMeta:
    name: str
    domain: Domain
    required_fields: List[str]


class IntentRegistry:
    def __init__(self):
        self._registry: Dict[str, IntentMeta] = {}

    def register(self, name: str, domain: Domain, required: List[str]):
        self._registry[name] = IntentMeta(name, domain, required)

    def get(self, name: str) -> Optional[IntentMeta]:
        return self._registry.get(name)

    def all(self):
        return self._registry


# ==============================
# REGISTER ENTERPRISE INTENTS
# ==============================

registry = IntentRegistry()

# POLICY
registry.register("GET_POLICY_BY_REGION", Domain.POLICY, ["project", "mpu", "region"])
registry.register("LIST_REGIONS", Domain.POLICY, ["project", "mpu"])
registry.register("LIST_DYNAMIC_RGS", Domain.POLICY, ["project", "mpu"])
registry.register("RG_VIEW", Domain.POLICY, ["project", "mpu"])
registry.register("GET_CURRENT_POLICY", Domain.POLICY, ["project"])

# HARDWARE
registry.register("CHECK_GRANULARITY", Domain.HARDWARE, ["project", "mpu"])
registry.register("CHECK_VMID_ACR", Domain.HARDWARE, ["project"])
registry.register("CHECK_ADDR_BUS_OFFSET", Domain.HARDWARE, ["project"])
registry.register("CHECK_40BIT_WIDTH", Domain.HARDWARE, ["project"])

# REGISTER
registry.register("REGISTER_LOOKUP", Domain.REGISTER, ["project", "register"])
registry.register("REGISTER_RANGE_LOOKUP", Domain.REGISTER, ["project", "start_addr", "end_addr"])
registry.register("REGISTER_XPU_LOOKUP", Domain.REGISTER, ["project", "register"])

# SUMMARY
registry.register("XPU_SUMMARY", Domain.SUMMARY, ["project"])


# ==============================
# VALIDATION ENGINE
# ==============================

class ValidationResult:
    def __init__(self, valid: bool, missing: Optional[List[str]] = None):
        self.valid = valid
        self.missing = missing or []


class IntentEngine:

    def __init__(self, registry: IntentRegistry):
        self.registry = registry

    def validate(self, intent_name: str, entities: Dict[str, Any]) -> ValidationResult:
        meta = self.registry.get(intent_name)
        if not meta:
            return ValidationResult(False, ["intent"])

        missing = []
        for field in meta.required_fields:
            if not entities.get(field):
                missing.append(field)

        return ValidationResult(valid=len(missing) == 0, missing=missing)