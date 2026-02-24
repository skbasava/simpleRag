“””
Multi-Agent Workflow — Project Lookup → MPU Fetch → Validation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Redis key structure (from your Redis Browser screenshots)
─────────────────────────────────────────────────────────
Project store (cross-thread):
cache:project:name:{PROJECT_NAME}  → STRING  (e.g. “642”)     ← name → id
cache:project:id:{PROJECT_ID}      → STRING  (e.g. “KAANAPALI_V2”) ← id → name

MPU store (cross-thread):
mpu:{project_id}:{version}:{component}  → STRING  (e.g. “0x00400000”)

Examples from your screenshots:
cache:project:name:ADRASTEA          → “101”
cache:project:name:AIC100 (QRANIUM)  → “642”
cache:project:id:642                 → “AIC100 (QRANIUM)”
mpu:642:5.5:ANOC_IPA_MPU_XPU4       → “0x00400000”
mpu:642:5.5:AOC_MPU_XPU4            → “0x00800000”

Workflow (3 agents in sequence)
────────────────────────────────
START
│
▼
project_lookup_node  (ProjectLookupAgent)
│  • Check cache:project:name:{name} → get project_id
│  • If NOT found → call load_projects_to_redis() → retry lookup
│  • Output: resolved project_id
│
▼
fetch_node  (FetchAgent)
│  • SCAN mpu:{project_id}:{version}:* → get all components
│  • If NOT found → call warehouse_fetch_mpu → write back to Redis
│  • Output: {component: value} dict
│
▼
validate_node  (ValidatorAgent)
│  • Completeness, format, regression checks
│  • If project not in Redis → trigger reload (routes back to project_lookup)
│  • Verdict: PASS / FLAG / REJECT
│
├── PASS   → end_pass   → END
├── FLAG   → fetch_node (retry ≤ MAX_RETRIES)
└── REJECT → end_reject → END
“””

import asyncio
import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, TypedDict

# ── LangGraph ─────────────────────────────────────────────────────────────────

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

# ── LangChain ─────────────────────────────────────────────────────────────────

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage,
)
from langchain_core.tools import tool

# ── Redis ─────────────────────────────────────────────────────────────────────

from redis.asyncio import Redis, ConnectionPool

# ─────────────────────────────────────────────────────────────────────────────

# LOGGING

# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(name)s - %(message)s”,
)
logger = logging.getLogger(**name**)

# ─────────────────────────────────────────────────────────────────────────────

# CONFIG

# ─────────────────────────────────────────────────────────────────────────────

REDIS_HOST     = os.getenv(“REDIS_HOST”, “10.79.1.51”)
REDIS_PORT     = int(os.getenv(“REDIS_PORT”, 6379))
REDIS_PASSWORD = os.getenv(“REDIS_PASSWORD”, None)
REDIS_DB       = int(os.getenv(“REDIS_DB”, 0))
REDIS_MAX_CONN = int(os.getenv(“REDIS_MAX_CONNECTIONS”, 50))
OPENAI_API_KEY = os.getenv(“OPENAI_API_KEY”, “your-api-key-here”)
SESSION_TTL    = int(os.getenv(“SESSION_TTL_SECONDS”, 3600))

MIN_COMPONENTS = 3      # reject if fewer components found
MAX_RETRIES    = 2      # max validate→fetch retries

# ─────────────────────────────────────────────────────────────────────────────

# REDIS KEY SCHEMA  — single place that owns all key patterns

# ─────────────────────────────────────────────────────────────────────────────

class RedisKeys:
“”“Encapsulates every key pattern used in the system.”””

```
# Project store
@staticmethod
def project_by_name(name: str) -> str:
    """cache:project:name:AIC100 (QRANIUM)  →  "642" """
    return f"cache:project:name:{name.strip()}"

@staticmethod
def project_by_id(project_id: str) -> str:
    """cache:project:id:642  →  "AIC100 (QRANIUM)" """
    return f"cache:project:id:{project_id.strip()}"

# MPU store
@staticmethod
def mpu_component(project_id: str, version: str, component: str) -> str:
    """mpu:642:5.5:ANOC_IPA_MPU_XPU4  →  "0x00400000" """
    return f"mpu:{project_id}:{version}:{component}"

@staticmethod
def mpu_prefix(project_id: str, version: str) -> str:
    """mpu:642:5.5:*"""
    return f"mpu:{project_id}:{version}:"

@staticmethod
def mpu_project_prefix(project_id: str) -> str:
    """mpu:642:*  — for listing all versions"""
    return f"mpu:{project_id}:"

@staticmethod
def all_project_names_prefix() -> str:
    """cache:project:name:*"""
    return "cache:project:name:*"

@staticmethod
def parse_mpu_key(full_key: str) -> Optional[dict]:
    """'mpu:642:5.5:ANOC_IPA_MPU_XPU4' → {project_id, version, component}"""
    parts = full_key.split(":", 3)
    if len(parts) == 4 and parts[0] == "mpu":
        return {"project_id": parts[1], "version": parts[2], "component": parts[3]}
    return None

@staticmethod
def parse_project_name_key(full_key: str) -> Optional[str]:
    """'cache:project:name:ADRASTEA' → 'ADRASTEA'"""
    prefix = "cache:project:name:"
    return full_key[len(prefix):] if full_key.startswith(prefix) else None
```

K = RedisKeys()   # module-level shorthand

# ─────────────────────────────────────────────────────────────────────────────

# REDIS CLIENT

# ─────────────────────────────────────────────────────────────────────────────

def create_redis_client() -> Redis:
pool = ConnectionPool(
host=REDIS_HOST,
port=REDIS_PORT,
password=REDIS_PASSWORD,
db=REDIS_DB,
max_connections=REDIS_MAX_CONN,
decode_responses=True,
socket_timeout=10,
socket_connect_timeout=5,
retry_on_timeout=True,
health_check_interval=30,
)
return Redis(connection_pool=pool)

# ─────────────────────────────────────────────────────────────────────────────

# PROJECT STORE  — wraps cache:project:* keys

# ─────────────────────────────────────────────────────────────────────────────

class ProjectStore:
“””
Manages the project name ↔ id mapping in Redis.

```
cache:project:name:{PROJECT_NAME} → project_id  (STRING)
cache:project:id:{PROJECT_ID}     → project_name (STRING)
"""

def __init__(self, client: Redis):
    self._r = client

async def get_id_by_name(self, project_name: str) -> Optional[str]:
    return await self._r.get(K.project_by_name(project_name))

async def get_name_by_id(self, project_id: str) -> Optional[str]:
    return await self._r.get(K.project_by_id(project_id))

async def project_exists(self, project_name: str) -> bool:
    return await self.get_id_by_name(project_name) is not None

async def set_project(self, project_name: str, project_id: str) -> None:
    """Write both directions of the mapping atomically via pipeline."""
    pipe = self._r.pipeline(transaction=True)
    pipe.set(K.project_by_name(project_name), project_id)
    pipe.set(K.project_by_id(project_id), project_name)
    await pipe.execute()
    logger.debug("project store: %s ↔ %s", project_name, project_id)

async def bulk_load(self, projects: Dict[str, str]) -> int:
    """
    Load {project_name: project_id} dict into Redis.
    Writes both cache:project:name:* and cache:project:id:* keys.
    """
    pipe = self._r.pipeline(transaction=False)
    for name, pid in projects.items():
        pipe.set(K.project_by_name(name), pid)
        pipe.set(K.project_by_id(pid), name)
    await pipe.execute()
    logger.info("project store: bulk loaded %d projects", len(projects))
    return len(projects)

async def list_all(self) -> Dict[str, str]:
    """Return {project_name: project_id} for all stored projects."""
    cursor  = 0
    results = {}
    while True:
        cursor, keys = await self._r.scan(
            cursor, match=K.all_project_names_prefix(), count=500
        )
        for full_key in keys:
            name = K.parse_project_name_key(full_key)
            if name:
                pid = await self._r.get(full_key)
                if pid:
                    results[name] = pid
        if cursor == 0:
            break
    return results

async def count(self) -> int:
    cursor = count = 0
    while True:
        cursor, keys = await self._r.scan(
            cursor, match=K.all_project_names_prefix(), count=500
        )
        count += len(keys)
        if cursor == 0:
            break
    return count
```

# ─────────────────────────────────────────────────────────────────────────────

# MPU STORE  — wraps mpu:{project_id}:{version}:* keys

# ─────────────────────────────────────────────────────────────────────────────

class MPUStore:
“”“Manages mpu:{project_id}:{version}:{component} STRING keys.”””

```
def __init__(self, client: Redis):
    self._r = client

async def get_component(self, project_id: str, version: str, component: str) -> Optional[str]:
    return await self._r.get(K.mpu_component(project_id, version, component))

async def get_all_components(self, project_id: str, version: str) -> Dict[str, str]:
    """SCAN mpu:{project_id}:{version}:* → {component: value}"""
    prefix  = K.mpu_prefix(project_id, version)
    results = {}
    cursor  = 0
    while True:
        cursor, keys = await self._r.scan(cursor, match=f"{prefix}*", count=200)
        for full_key in keys:
            parsed = K.parse_mpu_key(full_key)
            if parsed:
                val = await self._r.get(full_key)
                results[parsed["component"]] = val or ""
        if cursor == 0:
            break
    return results

async def set_all_components(
    self,
    project_id: str,
    version: str,
    components: Dict[str, str],
) -> int:
    """Pipeline write of all component keys."""
    pipe = self._r.pipeline(transaction=False)
    for component, value in components.items():
        pipe.set(K.mpu_component(project_id, version, component), value)
    await pipe.execute()
    logger.info("mpu store: wrote %d keys  project=%s  version=%s",
                len(components), project_id, version)
    return len(components)

async def list_versions(self, project_id: str) -> List[str]:
    prefix   = K.mpu_project_prefix(project_id)
    cursor   = 0
    versions = set()
    while True:
        cursor, keys = await self._r.scan(cursor, match=f"{prefix}*", count=200)
        for full_key in keys:
            parsed = K.parse_mpu_key(full_key)
            if parsed:
                versions.add(parsed["version"])
        if cursor == 0:
            break
    return sorted(versions)

async def compare_versions(
    self,
    project_id: str,
    version_a: str,
    version_b: str,
) -> dict:
    comps_a = await self.get_all_components(project_id, version_a)
    comps_b = await self.get_all_components(project_id, version_b)
    keys_a, keys_b = set(comps_a), set(comps_b)
    return {
        "added":   {k: comps_b[k] for k in keys_b - keys_a},
        "removed": {k: comps_a[k] for k in keys_a - keys_b},
        "changed": {
            k: {"from": comps_a[k], "to": comps_b[k]}
            for k in keys_a & keys_b if comps_a[k] != comps_b[k]
        },
    }
```

# ─────────────────────────────────────────────────────────────────────────────

# WORKFLOW STATE

# ─────────────────────────────────────────────────────────────────────────────

class WorkflowState(TypedDict):
# ── inputs ────────────────────────────────────────────────────────────────
session_id:    str
project_name:  str          # human name e.g. “AIC100 (QRANIUM)”
version:       str          # e.g. “5.5”

```
# ── project lookup ────────────────────────────────────────────────────────
project_id:          Optional[str]   # resolved from Redis e.g. "642"
project_found:       bool
projects_loaded:     bool            # True once bulk-load has run this session

# ── fetch agent ───────────────────────────────────────────────────────────
fetch_messages:  List[BaseMessage]
fetched_data:    Optional[Dict[str, str]]
fetch_source:    Optional[str]       # "redis_cache" | "warehouse"

# ── validator agent ───────────────────────────────────────────────────────
validate_messages: List[BaseMessage]
validation_result: Optional[str]     # "pass" | "flag" | "reject"
validation_reason: Optional[str]
issues:            List[str]

# ── control ───────────────────────────────────────────────────────────────
retry_count: int
error:       Optional[str]
```

# ─────────────────────────────────────────────────────────────────────────────

# MODULE-LEVEL STORE HANDLES  (set during initialisation)

# ─────────────────────────────────────────────────────────────────────────────

_project_store: Optional[ProjectStore] = None
_mpu_store:     Optional[MPUStore]     = None

# ─────────────────────────────────────────────────────────────────────────────

# WAREHOUSE STUB  (replace with your real API/DB calls)

# ─────────────────────────────────────────────────────────────────────────────

async def warehouse_load_all_projects() -> Dict[str, str]:
“””
Load all projects from the data warehouse.
Returns {project_name: project_id}.
TODO: replace with real DB/API call.
“””
await asyncio.sleep(0.05)
return {
“ADRASTEA”:            “101”,
“AGIOS”:               “202”,
“AGREUS”:              “303”,
“AIC100 (QRANIUM) V2”: “641”,
“AIC100 (QRANIUM)”:    “642”,
“AIC200 (NORDDC)”:     “643”,
“ALDABRA”:             “404”,
}

async def warehouse_fetch_mpu(project_id: str, version: str) -> Dict[str, str]:
“””
Fetch all MPU components for a project+version from the data warehouse.
Returns {component_name: hex_address}.
TODO: replace with real DB/API call.
“””
await asyncio.sleep(0.05)
return {
“ANOC_IPA_MPU_XPU4”:    “0x00400000”,
“AOC_MPU_XPU4”:         “0x00800000”,
“AOPSS_MPU_XPU4”:       “0x00C00000”,
“AOSS_PERIPH_MPU_XPU4”: “0x01000000”,
“BOOT_ROM_XPU4”:        “0x01400000”,
“BROADCAST_MPU_XPU4”:   “0x01800000”,
“CMSR_MPU_REGS_XPU4”:   “0x01C00000”,
}

# ─────────────────────────────────────────────────────────────────────────────

# TOOLS  — used by the agents

# ─────────────────────────────────────────────────────────────────────────────

@tool
async def tool_lookup_project_by_name(project_name: str) -> str:
“””
Look up a project in Redis by its name.
Checks key: cache:project:name:{project_name}
Returns project_id if found, or indicates not found.
“””
if not _project_store:
return json.dumps({“found”: False, “error”: “store not initialised”})
pid = await _project_store.get_id_by_name(project_name)
if pid:
return json.dumps({“found”: True, “project_name”: project_name, “project_id”: pid})
return json.dumps({“found”: False, “project_name”: project_name,
“message”: “Project not in Redis — trigger load_all_projects”})

@tool
async def tool_load_all_projects_to_redis() -> str:
“””
Load ALL projects from the data warehouse into Redis.
Writes cache:project:name:{name} and cache:project:id:{id} for every project.
Call this when a project is not found in Redis.
“””
if not _project_store:
return json.dumps({“error”: “store not initialised”})
projects = await warehouse_load_all_projects()
count    = await _project_store.bulk_load(projects)
return json.dumps({
“loaded”:    count,
“projects”:  list(projects.keys()),
“message”:  f”Loaded {count} projects into Redis. Retry lookup now.”,
})

@tool
async def tool_list_projects_in_redis() -> str:
“”“List all projects currently stored in Redis (cache:project:name:*).”””
if not _project_store:
return json.dumps({“error”: “store not initialised”})
all_projects = await _project_store.list_all()
return json.dumps({
“count”:    len(all_projects),
“projects”: all_projects,   # {name: id}
})

@tool
async def tool_get_mpu_components(project_id: str, version: str) -> str:
“””
Scan Redis for all MPU components of a project+version.
Pattern: mpu:{project_id}:{version}:*
Returns {component: value} dict. Empty dict = cache miss.
“””
if not _mpu_store:
return json.dumps({“error”: “store not initialised”})
components = await _mpu_store.get_all_components(project_id, version)
return json.dumps({
“project_id”: project_id,
“version”:    version,
“count”:      len(components),
“components”: components,
“cache_hit”:  len(components) > 0,
})

@tool
async def tool_load_mpu_from_warehouse(project_id: str, version: str) -> str:
“””
Fetch MPU components from the data warehouse and write them to Redis.
Call this only after a Redis cache miss on mpu:{project_id}:{version}:*
“””
if not _mpu_store:
return json.dumps({“error”: “store not initialised”})
components = await warehouse_fetch_mpu(project_id, version)
count      = await _mpu_store.set_all_components(project_id, version, components)
return json.dumps({
“project_id”: project_id,
“version”:    version,
“loaded”:     count,
“components”: components,
“source”:     “warehouse”,
})

@tool
async def tool_list_mpu_versions(project_id: str) -> str:
“”“List all MPU versions stored in Redis for a project.”””
if not _mpu_store:
return json.dumps({“error”: “store not initialised”})
versions = await _mpu_store.list_versions(project_id)
return json.dumps({“project_id”: project_id, “versions”: versions})

@tool
async def tool_compare_mpu_versions(project_id: str, version_a: str, version_b: str) -> str:
“”“Compare MPU components between two versions — detects regressions.”””
if not _mpu_store:
return json.dumps({“error”: “store not initialised”})
diff = await _mpu_store.compare_versions(project_id, version_a, version_b)
diff[“project_id”] = project_id
diff[“version_a”]  = version_a
diff[“version_b”]  = version_b
diff[“summary”]    = {
“added”:   len(diff[“added”]),
“removed”: len(diff[“removed”]),
“changed”: len(diff[“changed”]),
}
return json.dumps(diff)

# Tool sets per agent

project_lookup_tools = [
tool_lookup_project_by_name,
tool_load_all_projects_to_redis,
tool_list_projects_in_redis,
]
fetch_tools = [
tool_get_mpu_components,
tool_load_mpu_from_warehouse,
]
validator_tools = [
tool_get_mpu_components,
tool_list_mpu_versions,
tool_compare_mpu_versions,
tool_lookup_project_by_name,        # validator can also verify project exists
tool_load_all_projects_to_redis,    # validator can trigger reload if needed
]

# ─────────────────────────────────────────────────────────────────────────────

# LLMs  (one per agent role)

# ─────────────────────────────────────────────────────────────────────────────

def make_llm(tools_list: list) -> ChatOpenAI:
return ChatOpenAI(
model=“gpt-4o-mini”, temperature=0,
api_key=OPENAI_API_KEY, streaming=False,
).bind_tools(tools_list)

_project_lookup_llm = make_llm(project_lookup_tools)
_fetch_llm          = make_llm(fetch_tools)
_validator_llm      = make_llm(validator_tools)

# ─────────────────────────────────────────────────────────────────────────────

# REACT LOOP HELPER

# ─────────────────────────────────────────────────────────────────────────────

async def react_loop(
llm,
tools_list: list,
history: List[BaseMessage],
max_rounds: int = 8,
) -> tuple[Optional[AIMessage], List[BaseMessage]]:
“””
Runs the ReAct (Reason + Act) loop until the LLM stops calling tools.
Returns (final_ai_message, updated_history).
“””
tool_map = {t.name: t for t in tools_list}
response = None

```
for _ in range(max_rounds):
    response = await llm.ainvoke(history)
    history.append(response)

    if not (hasattr(response, "tool_calls") and response.tool_calls):
        break   # no more tool calls → final answer

    for tc in response.tool_calls:
        fn     = tool_map.get(tc["name"])
        result = (
            await fn.ainvoke(tc["args"])
            if fn
            else json.dumps({"error": f"unknown tool: {tc['name']}"})
        )
        history.append(ToolMessage(content=result, tool_call_id=tc["id"]))

return response, history
```

def extract_json(text: str) -> Optional[dict]:
“”“Pull the first JSON object out of an LLM response string.”””
try:
start = text.find(”{”)
end   = text.rfind(”}”) + 1
if start >= 0 and end > start:
return json.loads(text[start:end])
except (json.JSONDecodeError, ValueError):
pass
return None

# ─────────────────────────────────────────────────────────────────────────────

# NODE 1 — PROJECT LOOKUP AGENT

# ─────────────────────────────────────────────────────────────────────────────

async def project_lookup_node(state: WorkflowState) -> dict:
“””
ProjectLookupAgent
──────────────────
Step 1: Check cache:project:name:{project_name} in Redis.
Step 2: If NOT found → call tool_load_all_projects_to_redis → retry lookup.
Step 3: Return project_id and project_found flag.

```
This ensures the project catalogue is always in Redis before MPU fetching.
"""
project_name = state["project_name"]

# Quick direct check first (avoids LLM call on cache hit)
if _project_store:
    pid = await _project_store.get_id_by_name(project_name)
    if pid:
        logger.info("[ProjectLookup] cache HIT  '%s' → id=%s", project_name, pid)
        return {
            "project_id":      pid,
            "project_found":   True,
            "projects_loaded": state.get("projects_loaded", False),
        }

# Cache miss — let the LLM agent handle load + retry
logger.info("[ProjectLookup] cache MISS  '%s' — invoking agent", project_name)

project_count = (await _project_store.count()) if _project_store else 0
system = SystemMessage(content=(
    "You are ProjectLookupAgent.\n\n"
    "Your job: resolve a project name to its project_id stored in Redis.\n\n"
    "Redis key: cache:project:name:{project_name}  →  project_id (STRING)\n\n"
    "Steps:\n"
    "1. Call tool_lookup_project_by_name.\n"
    "2. If NOT found AND projects have not been loaded yet:\n"
    "   → Call tool_load_all_projects_to_redis to populate Redis from warehouse.\n"
    "   → Then call tool_lookup_project_by_name again.\n"
    "3. Respond ONLY with JSON:\n"
    '   {"found": true|false, "project_name": "...", "project_id": "..."}\n\n'
    f"Current project count in Redis: {project_count}\n"
    f"Projects already loaded this session: {state.get('projects_loaded', False)}"
))

messages = [HumanMessage(
    content=f"Lookup project: '{project_name}'"
)]

_, history = await react_loop(
    _project_lookup_llm, project_lookup_tools, [system] + messages
)

final_ai    = next((m for m in reversed(history) if isinstance(m, AIMessage)), None)
result      = extract_json(final_ai.content if final_ai else "") or {}

found      = result.get("found", False)
project_id = result.get("project_id")

# Also check if a load was triggered during this run
loaded_this_run = any(
    isinstance(m, ToolMessage) and
    "loaded" in m.content and "projects" in m.content
    for m in history
)

logger.info(
    "[ProjectLookup] project='%s'  found=%s  id=%s  loaded_this_run=%s",
    project_name, found, project_id, loaded_this_run,
)

return {
    "project_id":      project_id if found else None,
    "project_found":   found,
    "projects_loaded": state.get("projects_loaded", False) or loaded_this_run,
}
```

# ─────────────────────────────────────────────────────────────────────────────

# NODE 2 — FETCH AGENT

# ─────────────────────────────────────────────────────────────────────────────

async def fetch_node(state: WorkflowState) -> dict:
“””
FetchAgent
──────────
Step 1: SCAN mpu:{project_id}:{version}:* in Redis.
Step 2: If components found → return from cache (no warehouse call).
Step 3: If empty → call tool_load_mpu_from_warehouse → write to Redis.
Step 4: Return fetched_data {component: value} and fetch_source.
“””
project_id = state.get(“project_id”)
version    = state[“version”]

```
if not project_id:
    return {
        "fetched_data": {},
        "fetch_source": "error",
        "error":        "project_id not resolved — project lookup failed",
    }

# Quick direct check first
if _mpu_store:
    components = await _mpu_store.get_all_components(project_id, version)
    if components:
        logger.info(
            "[FetchAgent] cache HIT  project=%s  version=%s  components=%d",
            project_id, version, len(components),
        )
        return {
            "fetched_data": components,
            "fetch_source": "redis_cache",
            "fetch_messages": [],
        }

# Cache miss — let agent handle warehouse fetch + write-back
logger.info("[FetchAgent] cache MISS  project=%s  version=%s", project_id, version)

system = SystemMessage(content=(
    "You are FetchAgent.\n\n"
    "Your job: retrieve all MPU components for a project+version.\n\n"
    "Redis key pattern: mpu:{project_id}:{version}:{component}  →  STRING value\n\n"
    "Steps:\n"
    "1. Call tool_get_mpu_components to check Redis.\n"
    "2. If cache_hit is true → return the components as-is.\n"
    "3. If cache_hit is false → call tool_load_mpu_from_warehouse to fetch + write to Redis.\n"
    "4. Respond ONLY with JSON:\n"
    '   {"source": "redis_cache"|"warehouse", "components": {...}, "count": N}\n'
))

messages = [HumanMessage(
    content=f"Fetch MPU components: project_id={project_id}, version={version}"
)]

_, history = await react_loop(_fetch_llm, fetch_tools, [system] + messages)

final_ai     = next((m for m in reversed(history) if isinstance(m, AIMessage)), None)
result       = extract_json(final_ai.content if final_ai else "") or {}
fetched_data = result.get("components", {})
fetch_source = result.get("source", "unknown")

logger.info(
    "[FetchAgent] project=%s  version=%s  source=%s  components=%d",
    project_id, version, fetch_source, len(fetched_data),
)

return {
    "fetch_messages": history[1:],
    "fetched_data":   fetched_data,
    "fetch_source":   fetch_source,
}
```

# ─────────────────────────────────────────────────────────────────────────────

# NODE 3 — VALIDATOR AGENT

# ─────────────────────────────────────────────────────────────────────────────

async def validate_node(state: WorkflowState) -> dict:
“””
ValidatorAgent
──────────────
Validates fetched MPU data:
1. Project existence  — verify project_id is properly resolved
2. Completeness       — must have ≥ MIN_COMPONENTS components
3. Format             — values must be hex strings (0x…)
4. Empty values       — flag any blank/null entries
5. Regression check   — compare vs prior version if available in Redis
6. If project missing — trigger reload via tool_load_all_projects_to_redis
“””
project_id   = state.get(“project_id”)
project_name = state[“project_name”]
version      = state[“version”]
fetched_data = state.get(“fetched_data”) or {}

```
system = SystemMessage(content=(
    "You are ValidatorAgent. Validate MPU data with strict rules.\n\n"
    "VALIDATION RULES:\n"
    f"  PROJECT EXISTS : call tool_lookup_project_by_name to verify\n"
    "                   If not found → call tool_load_all_projects_to_redis → recheck\n"
    f"  COMPLETENESS   : must have ≥ {MIN_COMPONENTS} components   → REJECT if fewer\n"
    "  FORMAT         : values must be hex strings (0x...)         → FLAG if not\n"
    "  EMPTY VALUES   : any blank/null value                       → FLAG\n"
    "  REGRESSION     : call tool_list_mpu_versions to find prior version\n"
    "                   If found → call tool_compare_mpu_versions\n"
    "                   Flag if changed components detected\n\n"
    "STEPS:\n"
    "1. Verify project exists in Redis.\n"
    "2. Apply completeness + format rules to the provided data.\n"
    "3. Check for prior versions and run regression diff.\n"
    "4. Decide verdict.\n"
    "5. Respond ONLY with JSON:\n"
    '   {"result": "pass"|"flag"|"reject", "issues": [...], "reason": "..."}\n'
))

messages = [HumanMessage(content=(
    f"Validate MPU data:\n"
    f"  project_name = {project_name}\n"
    f"  project_id   = {project_id}\n"
    f"  version      = {version}\n"
    f"  fetch_source = {state.get('fetch_source')}\n"
    f"  component_count = {len(fetched_data)}\n\n"
    f"Components:\n{json.dumps(fetched_data, indent=2)}"
))]

_, history = await react_loop(_validator_llm, validator_tools, [system] + messages)

final_ai = next((m for m in reversed(history) if isinstance(m, AIMessage)), None)
verdict  = extract_json(final_ai.content if final_ai else "") or {
    "result": "reject", "issues": ["parse_failed"], "reason": "could not parse verdict"
}

result = verdict.get("result", "reject")
issues = verdict.get("issues", [])
reason = verdict.get("reason", "")

logger.info(
    "[ValidatorAgent] project=%s  version=%s  result=%s  issues=%s",
    project_name, version, result, issues,
)

return {
    "validate_messages": history[1:],
    "validation_result": result,
    "validation_reason": reason,
    "issues":            issues,
}
```

# ─────────────────────────────────────────────────────────────────────────────

# ROUTING FUNCTIONS

# ─────────────────────────────────────────────────────────────────────────────

def route_after_lookup(
state: WorkflowState,
) -> Literal[“fetch_node”, “end_reject”]:
“”“After project lookup: proceed to fetch or hard-fail.”””
if state.get(“project_found”) and state.get(“project_id”):
return “fetch_node”
logger.error(
“[Router] project ‘%s’ not found even after reload → rejecting”,
state[“project_name”],
)
return “end_reject”

def route_after_validation(
state: WorkflowState,
) -> Literal[“fetch_node”, “end_pass”, “end_reject”]:
“”“After validation: pass, retry, or reject.”””
result      = state.get(“validation_result”, “reject”)
retry_count = state.get(“retry_count”, 0)

```
if result == "pass":
    return "end_pass"

if result == "flag":
    if retry_count < MAX_RETRIES:
        logger.warning(
            "[Router] FLAGGED — retry %d/%d  project=%s",
            retry_count + 1, MAX_RETRIES, state["project_name"],
        )
        return "fetch_node"
    logger.error("[Router] max retries reached → rejecting")
    return "end_reject"

return "end_reject"
```

async def bump_retry(state: WorkflowState) -> dict:
return {“retry_count”: state.get(“retry_count”, 0) + 1}

# ─────────────────────────────────────────────────────────────────────────────

# TERMINAL NODES

# ─────────────────────────────────────────────────────────────────────────────

async def end_pass_node(state: WorkflowState) -> dict:
logger.info(
“✅ PASS  project=’%s’ (id=%s)  version=%s  components=%d  source=%s”,
state[“project_name”], state.get(“project_id”),
state[“version”], len(state.get(“fetched_data”) or {}),
state.get(“fetch_source”),
)
return {}

async def end_reject_node(state: WorkflowState) -> dict:
logger.error(
“❌ REJECT  project=’%s’ (id=%s)  version=%s  reason=’%s’  issues=%s”,
state[“project_name”], state.get(“project_id”),
state[“version”], state.get(“validation_reason”), state.get(“issues”),
)
return {“error”: state.get(“validation_reason”) or state.get(“error”) or “failed”}

# ─────────────────────────────────────────────────────────────────────────────

# BUILD WORKFLOW GRAPH

# ─────────────────────────────────────────────────────────────────────────────

def build_workflow(checkpointer: AsyncRedisSaver) -> StateGraph:
“””
Full workflow graph
───────────────────
START
│
▼
project_lookup_node ──── not found ──────────────────▶ end_reject
│ found
▼
fetch_node  ◀────────────────────────────────────┐
│                                              │ (flag + retry < MAX)
▼                                              │
validate_node                                    │
│                                              │
├── “pass”   ──▶ end_pass   ──▶ END            │
├── “flag”   ──────────────────────────────────┘
└── “reject” ──▶ end_reject ──▶ END
“””
g = StateGraph(WorkflowState)

```
g.add_node("project_lookup_node", project_lookup_node)
g.add_node("fetch_node",          fetch_node)
g.add_node("validate_node",       validate_node)
g.add_node("end_pass",            end_pass_node)
g.add_node("end_reject",          end_reject_node)

g.set_entry_point("project_lookup_node")

g.add_conditional_edges(
    "project_lookup_node",
    route_after_lookup,
    {"fetch_node": "fetch_node", "end_reject": "end_reject"},
)

g.add_edge("fetch_node", "validate_node")

g.add_conditional_edges(
    "validate_node",
    route_after_validation,
    {
        "fetch_node":   "fetch_node",
        "end_pass":     "end_pass",
        "end_reject":   "end_reject",
    },
)

g.add_edge("end_pass",   END)
g.add_edge("end_reject", END)

return g.compile(checkpointer=checkpointer)
```

# ─────────────────────────────────────────────────────────────────────────────

# PUBLIC RUN FUNCTION

# ─────────────────────────────────────────────────────────────────────────────

async def run_workflow(
project_name: str,
version:      str,
session_id:   str,
workflow:     StateGraph,
) -> WorkflowState:
config = {
“configurable”: {
“thread_id”:      session_id,
“checkpoint_ttl”: SESSION_TTL,
}
}
initial: WorkflowState = {
“session_id”:         session_id,
“project_name”:       project_name,
“version”:            version,
“project_id”:         None,
“project_found”:      False,
“projects_loaded”:    False,
“fetch_messages”:     [],
“fetched_data”:       None,
“fetch_source”:       None,
“validate_messages”:  [],
“validation_result”:  None,
“validation_reason”:  None,
“issues”:             [],
“retry_count”:        0,
“error”:              None,
}

```
final = None
async for snapshot in workflow.astream(initial, config, stream_mode="values"):
    final = snapshot
return final
```

# ─────────────────────────────────────────────────────────────────────────────

# DEMO

# ─────────────────────────────────────────────────────────────────────────────

async def main():
global _project_store, _mpu_store

```
redis_client = create_redis_client()
await redis_client.ping()
logger.info("Redis connected  %s:%s  db=%s", REDIS_HOST, REDIS_PORT, REDIS_DB)

_project_store = ProjectStore(redis_client)
_mpu_store     = MPUStore(redis_client)
checkpointer   = AsyncRedisSaver(redis_client)
workflow       = build_workflow(checkpointer)

divider = "═" * 68

# ── Run 1: project NOT in Redis → auto-load → resolve → fetch MPU ────────
print(f"\n{divider}")
print("RUN 1  project='AIC100 (QRANIUM)'  version=5.5  [cold start]")
print(f"{divider}")
r1 = await run_workflow("AIC100 (QRANIUM)", "5.5", "sess_001", workflow)
print(f"  project_id  : {r1.get('project_id')}")
print(f"  found       : {r1.get('project_found')}")
print(f"  fetch_source: {r1.get('fetch_source')}")
print(f"  components  : {len(r1.get('fetched_data') or {})}")
print(f"  validation  : {r1.get('validation_result')}")
print(f"  issues      : {r1.get('issues')}")

# ── Run 2: project now in Redis → fast lookup → MPU cache hit ────────────
print(f"\n{divider}")
print("RUN 2  project='AIC100 (QRANIUM)'  version=5.5  [cache hit]")
print(f"{divider}")
r2 = await run_workflow("AIC100 (QRANIUM)", "5.5", "sess_002", workflow)
print(f"  project_id  : {r2.get('project_id')}")
print(f"  fetch_source: {r2.get('fetch_source')}  ← should be redis_cache")
print(f"  components  : {len(r2.get('fetched_data') or {})}")
print(f"  validation  : {r2.get('validation_result')}")

# ── Run 3: unknown project → triggers load → not in warehouse → reject ───
print(f"\n{divider}")
print("RUN 3  project='UNKNOWN_PROJECT'  version=5.5  [not found]")
print(f"{divider}")
r3 = await run_workflow("UNKNOWN_PROJECT", "5.5", "sess_003", workflow)
print(f"  project_found: {r3.get('project_found')}")
print(f"  validation   : {r3.get('validation_result')}")
print(f"  error        : {r3.get('error')}")

# ── Run 4: concurrent sessions ────────────────────────────────────────────
print(f"\n{divider}")
print("RUN 4  3 concurrent sessions — different projects")
print(f"{divider}")
tasks = [
    run_workflow("ADRASTEA",            "5.5", "sess_101", workflow),
    run_workflow("AIC100 (QRANIUM) V2", "5.5", "sess_102", workflow),
    run_workflow("AIC200 (NORDDC)",     "5.5", "sess_103", workflow),
]
results = await asyncio.gather(*tasks)
for name, r in zip(["ADRASTEA", "AIC100 (QRANIUM) V2", "AIC200 (NORDDC)"], results):
    print(f"  {name:<25} id={r.get('project_id'):<5} "
          f"source={r.get('fetch_source'):<15} "
          f"result={r.get('validation_result')}")

# ── Final state of Redis stores ───────────────────────────────────────────
print(f"\n{divider}")
print("REDIS STATE — cache:project:name:*")
print(f"{divider}")
all_projects = await _project_store.list_all()
for name, pid in sorted(all_projects.items()):
    print(f"  cache:project:name:{name:<30} → {pid}")

print(f"\n{divider}")
print("REDIS STATE — mpu:* (component keys written this session)")
print(f"{divider}")
for pid in {r.get("project_id") for r in [r1,r2,r3] if r.get("project_id")}:
    versions = await _mpu_store.list_versions(pid)
    for v in versions:
        comps = await _mpu_store.get_all_components(pid, v)
        print(f"\n  project_id={pid}  version={v}  ({len(comps)} components)")
        for comp, val in sorted(comps.items()):
            print(f"    mpu:{pid}:{v}:{comp:<35} = {val}")

await redis_client.aclose()
logger.info("Done")
```

if **name** == “**main**”:
asyncio.run(main())