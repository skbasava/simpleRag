"""
IP Catalog — PostgreSQL Schema + Redis Cache Layout
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Data model derived from actual MPU JSON (screenshot):
  {
    "mpu": "ANOC_IPA_MPU_XPU4",
    "chip": 642,
    "version": "5.5",
    "hw": {
      "design": {
        "FF_MODULE": "ANOC_IPA_MPU_XPU4",
        "FF_ADDRESS": "0x01740000",
        "XPU4_REV:MAJOR": "4",  "XPU4_REV:MINOR": "2",  "XPU4_REV:STEP": "0",
        "NUM_RES_GRP": "16",
        "NUM_QAD": "11",
        "XPRESSCFG_EN": "0",
        "XPRESSCFG_MULTIDIE": "0",
        "XPU_TYPE": "0",
        "XPU4_IDR0:nRG": "15",
        "XPU4_IDR0:BLED": "0",
        "XPU4_IDR0:CLIENT_HALTREQACK_EN": "0",
        "XPU4_IDR0:CLIENT_PIPELINE_EN": "0",
        "XPU4_IDR0:xpressCfgMultiDie": "0",
        "XPU4_IDR0:xpressCfgEn": "0",
        "XPU4_IDR0:XPU_TYPE": "0",
        "XPU4_IDR1:CLIENT_ADDR_WIDTH": "35",
        "XPU4_IDR1:CONFIG_ADDR_WIDTH": "32",
        "XPU4_IDR1:ADDR_MSB": "35",
        "XPU4_IDR1:ADDR_LSB": "12",
        "XPU4_IDR2:SyncModeEn": "0",
        "XPU4_IDR2:ParityEn": "0",
        "XPU4_IDR2:useQsiCfgIntf": "0",
        "XPU4_IDR2:useQsiClientIntf": "0",
        "XPU4_IDR2:useAhbWrapper": "0",
        "XPU4_IDR2:useLegacyIntf": "0",
        "XPU4_IDR2:nQAD": "11",
        ...
      },
      "integration": {
        "InputMSB": "35"
      }
    }
  }

3-table design (normalised):
  projects          — project identity
  mpu_configs       — one row per MPU per project+version
  mpu_hw_design     — hardware design registers (IDR0/IDR1/IDR2 + params)
  mpu_hw_integration— integration params (InputMSB etc.)

Redis layout (hot-path cache):
  Exact lookups → Redis strings
  List queries  → Redis strings (JSON)
  Full metadata → Redis strings (JSON)
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import asyncpg
from redis.asyncio import Redis, ConnectionPool

logger = logging.getLogger(__name__)

POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://user:pass@localhost:5432/ip_catalog")
REDIS_HOST   = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT   = int(os.getenv("REDIS_PORT", 6379))


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — POSTGRESQL SCHEMA
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA_SQL = """

-- ── Table 1: projects ────────────────────────────────────────────────────────
-- One row per project (chip).
-- project_id matches "chip" field in the JSON (e.g. 642).
CREATE TABLE IF NOT EXISTS projects (
    project_id   INTEGER      PRIMARY KEY,          -- chip ID e.g. 642
    project_name VARCHAR(200) NOT NULL UNIQUE,      -- e.g. "AIC100 (QRANIUM)"
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── Table 2: project_versions ────────────────────────────────────────────────
-- Tracks which versions exist per project.
-- Separate table so we can list all versions for a project efficiently.
CREATE TABLE IF NOT EXISTS project_versions (
    id           SERIAL      PRIMARY KEY,
    project_id   INTEGER     NOT NULL REFERENCES projects(project_id),
    version      VARCHAR(20) NOT NULL,              -- e.g. "5.5"
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP   NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, version)
);

-- ── Table 3: mpu_configs ─────────────────────────────────────────────────────
-- One row per MPU per project+version.
-- Holds the top-level MPU fields from the JSON.
-- Key query patterns:
--   "List all MPUs for project X version Y"
--   "How many MPUs in project X?"
--   "Is xpresscfg_en set for MPU X?"
CREATE TABLE IF NOT EXISTS mpu_configs (
    id               SERIAL       PRIMARY KEY,
    project_id       INTEGER      NOT NULL REFERENCES projects(project_id),
    version          VARCHAR(20)  NOT NULL,
    mpu_name         VARCHAR(200) NOT NULL,         -- e.g. "ANOC_IPA_MPU_XPU4"

    -- Top-level hw.design fields — promoted to columns for fast querying
    ff_module        VARCHAR(200),                  -- FF_MODULE
    ff_address       VARCHAR(20),                   -- FF_ADDRESS e.g. "0x01740000"
    ff_address_int   BIGINT,                        -- FF_ADDRESS as integer for BETWEEN

    -- Revision
    xpu4_rev_major   SMALLINT,                      -- XPU4_REV:MAJOR
    xpu4_rev_minor   SMALLINT,                      -- XPU4_REV:MINOR
    xpu4_rev_step    SMALLINT,                      -- XPU4_REV:STEP

    -- Key config fields — promoted for direct query/filter without JSON scan
    num_res_grp      SMALLINT,                      -- NUM_RES_GRP (16) — "how many RGs?"
    num_qad          SMALLINT,                      -- NUM_QAD (11)
    xpresscfg_en     BOOLEAN NOT NULL DEFAULT FALSE,-- XPRESSCFG_EN — "is express cfg on?"
    xpresscfg_multidie BOOLEAN NOT NULL DEFAULT FALSE, -- XPRESSCFG_MULTIDIE
    xpu_type         SMALLINT,                      -- XPU_TYPE

    -- integration fields
    input_msb        SMALLINT,                      -- hw.integration.InputMSB

    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (project_id, version, mpu_name)
);

-- Indexes for the most common query patterns
CREATE INDEX IF NOT EXISTS idx_mpu_configs_project_version
    ON mpu_configs (project_id, version);

CREATE INDEX IF NOT EXISTS idx_mpu_configs_ff_address_int
    ON mpu_configs (project_id, version, ff_address_int);      -- address range lookup

CREATE INDEX IF NOT EXISTS idx_mpu_configs_xpresscfg
    ON mpu_configs (project_id, version, xpresscfg_en);        -- "which MPUs have express cfg?"


-- ── Table 4: mpu_hw_design ───────────────────────────────────────────────────
-- Stores ALL hw.design fields as key-value pairs.
-- Used when the full raw config is needed (e.g. show full MPU details).
-- Also stores IDR register fields (IDR0/IDR1/IDR2).
-- NOT used for filtering — promoted columns in mpu_configs handle that.
CREATE TABLE IF NOT EXISTS mpu_hw_design (
    id           SERIAL       PRIMARY KEY,
    project_id   INTEGER      NOT NULL REFERENCES projects(project_id),
    version      VARCHAR(20)  NOT NULL,
    mpu_name     VARCHAR(200) NOT NULL,
    param_key    VARCHAR(200) NOT NULL,    -- e.g. "XPU4_IDR0:nRG", "BLK_MAX_ADDRESS"
    param_value  VARCHAR(500) NOT NULL,    -- always stored as string, cast on read
    UNIQUE (project_id, version, mpu_name, param_key)
);

CREATE INDEX IF NOT EXISTS idx_mpu_hw_design_lookup
    ON mpu_hw_design (project_id, version, mpu_name);

-- ── Table 5: mpu_hw_integration ──────────────────────────────────────────────
-- Stores hw.integration fields separately (kept small — usually just InputMSB).
CREATE TABLE IF NOT EXISTS mpu_hw_integration (
    id           SERIAL       PRIMARY KEY,
    project_id   INTEGER      NOT NULL REFERENCES projects(project_id),
    version      VARCHAR(20)  NOT NULL,
    mpu_name     VARCHAR(200) NOT NULL,
    param_key    VARCHAR(200) NOT NULL,    -- e.g. "InputMSB"
    param_value  VARCHAR(500) NOT NULL,
    UNIQUE (project_id, version, mpu_name, param_key)
);

CREATE INDEX IF NOT EXISTS idx_mpu_hw_integration_lookup
    ON mpu_hw_integration (project_id, version, mpu_name);


-- ── View: mpu_summary ────────────────────────────────────────────────────────
-- Convenience view for the most common "show MPU details" query.
-- Avoids joins in application code for the hot read path.
CREATE OR REPLACE VIEW mpu_summary AS
SELECT
    mc.project_id,
    p.project_name,
    mc.version,
    mc.mpu_name,
    mc.ff_address,
    mc.xpu4_rev_major || '.' || mc.xpu4_rev_minor || '.' || mc.xpu4_rev_step
        AS xpu4_revision,
    mc.num_res_grp,
    mc.num_qad,
    mc.xpresscfg_en,
    mc.xpresscfg_multidie,
    mc.xpu_type,
    mc.input_msb
FROM mpu_configs mc
JOIN projects    p  ON p.project_id = mc.project_id
WHERE mc.is_active = TRUE;
"""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — REDIS KEY LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
"""
Redis key design (all strings — no Hashes or Sets needed):

project lookup
──────────────
  cache:project:name:{project_name}         → project_id (int as string)
  cache:project:id:{project_id}             → project_name
  cache:project:versions:{project_id}       → JSON ["5.4", "5.5", ...]

MPU list
────────
  cache:mpu:list:{project_id}:{version}     → JSON [
                                                {"mpu_name": ..., "ff_address": ...,
                                                 "num_res_grp": ..., "xpresscfg_en": ...},
                                                ...
                                              ]
  cache:mpu:count:{project_id}:{version}    → integer count of MPUs

MPU exact lookups (hot path — agents hit these on every request)
────────────────────────────────────────────────────────────────
  cache:mpu:rg_count:{pid}:{ver}:{mpu}      → NUM_RES_GRP  (integer string)
  cache:mpu:xpresscfg:{pid}:{ver}:{mpu}     → "1" or "0"
  cache:mpu:ff_address:{pid}:{ver}:{mpu}    → "0x01740000"
  cache:mpu:num_qad:{pid}:{ver}:{mpu}       → NUM_QAD      (integer string)

MPU full metadata (for "show full details" queries)
───────────────────────────────────────────────────
  cache:mpu:metadata:{pid}:{ver}:{mpu}      → JSON of full mpu_summary view row

No TTL set — static data, never expires.
Cache populated once at startup via warm_cache().
"""


class CacheKeys:
    # Project
    @staticmethod
    def project_by_name(name: str)         -> str: return f"cache:project:name:{name.strip()}"
    @staticmethod
    def project_by_id(pid: int)            -> str: return f"cache:project:id:{pid}"
    @staticmethod
    def project_versions(pid: int)         -> str: return f"cache:project:versions:{pid}"

    # MPU list + count
    @staticmethod
    def mpu_list(pid: int, ver: str)       -> str: return f"cache:mpu:list:{pid}:{ver}"
    @staticmethod
    def mpu_count(pid: int, ver: str)      -> str: return f"cache:mpu:count:{pid}:{ver}"

    # MPU exact fields (hot path)
    @staticmethod
    def mpu_rg_count(pid, ver, mpu)        -> str: return f"cache:mpu:rg_count:{pid}:{ver}:{mpu}"
    @staticmethod
    def mpu_xpresscfg(pid, ver, mpu)       -> str: return f"cache:mpu:xpresscfg:{pid}:{ver}:{mpu}"
    @staticmethod
    def mpu_ff_address(pid, ver, mpu)      -> str: return f"cache:mpu:ff_address:{pid}:{ver}:{mpu}"
    @staticmethod
    def mpu_num_qad(pid, ver, mpu)         -> str: return f"cache:mpu:num_qad:{pid}:{ver}:{mpu}"

    # MPU full metadata blob
    @staticmethod
    def mpu_metadata(pid, ver, mpu)        -> str: return f"cache:mpu:metadata:{pid}:{ver}:{mpu}"


K = CacheKeys()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — DATA STORE
# ─────────────────────────────────────────────────────────────────────────────
class IPCatalogStore:

    def __init__(self, pg: asyncpg.Pool, redis: Redis):
        self._pg    = pg
        self._redis = redis

    @classmethod
    async def create(cls, dsn: str, redis: Redis) -> "IPCatalogStore":
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        store = cls(pool, redis)
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        logger.info("IPCatalogStore ready")
        return store

    # ─────────────────────────────────────────────────────────────────────────
    # WRITE — load MPU JSON into PostgreSQL then Redis
    # ─────────────────────────────────────────────────────────────────────────
    async def load_mpu_json(self, mpu_json: dict) -> None:
        """
        Load one MPU JSON document (from the screenshot format) into
        PostgreSQL (all tables) and warm the Redis cache for this MPU.

        Input shape:
          {
            "mpu": "ANOC_IPA_MPU_XPU4",
            "chip": 642,
            "version": "5.5",
            "hw": {
              "design": { ... },
              "integration": { "InputMSB": "35" }
            }
          }
        """
        mpu_name   = mpu_json["mpu"]
        project_id = int(mpu_json["chip"])
        version    = mpu_json["version"]
        design     = mpu_json.get("hw", {}).get("design", {})
        integration= mpu_json.get("hw", {}).get("integration", {})

        async with self._pg.acquire() as conn:
            async with conn.transaction():

                # ── Ensure project_versions row exists ────────────────────────
                await conn.execute("""
                    INSERT INTO project_versions (project_id, version)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                """, project_id, version)

                # ── Parse promoted columns ────────────────────────────────────
                ff_address     = design.get("FF_ADDRESS", "")
                ff_address_int = int(ff_address, 16) if ff_address.startswith("0x") else None

                def _int(key):   return int(design[key])   if key in design else None
                def _bool(key):  return design.get(key, "0") != "0"
                    # ── Insert mpu_configs row ────────────────────────────────────
                await conn.execute("""
                    INSERT INTO mpu_configs (
                        project_id, version, mpu_name,
                        ff_module, ff_address, ff_address_int,
                        xpu4_rev_major, xpu4_rev_minor, xpu4_rev_step,
                        num_res_grp, num_qad,
                        xpresscfg_en, xpresscfg_multidie, xpu_type,
                        input_msb
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15
                    )
                    ON CONFLICT (project_id, version, mpu_name)
                    DO UPDATE SET
                        ff_module          = EXCLUDED.ff_module,
                        ff_address         = EXCLUDED.ff_address,
                        ff_address_int     = EXCLUDED.ff_address_int,
                        xpu4_rev_major     = EXCLUDED.xpu4_rev_major,
                        xpu4_rev_minor     = EXCLUDED.xpu4_rev_minor,
                        xpu4_rev_step      = EXCLUDED.xpu4_rev_step,
                        num_res_grp        = EXCLUDED.num_res_grp,
                        num_qad            = EXCLUDED.num_qad,
                        xpresscfg_en       = EXCLUDED.xpresscfg_en,
                        xpresscfg_multidie = EXCLUDED.xpresscfg_multidie,
                        xpu_type           = EXCLUDED.xpu_type,
                        input_msb          = EXCLUDED.input_msb
                """,
                    project_id, version, mpu_name,
                    design.get("FF_MODULE"),
                    ff_address,
                    ff_address_int,
                    _int("XPU4_REV:MAJOR"), _int("XPU4_REV:MINOR"), _int("XPU4_REV:STEP"),
                    _int("NUM_RES_GRP"), _int("NUM_QAD"),
                    _bool("XPRESSCFG_EN"), _bool("XPRESSCFG_MULTIDIE"),
                    _int("XPU_TYPE"),
                    int(integration["InputMSB"]) if "InputMSB" in integration else None,
                )

                # ── Bulk-insert ALL hw.design fields as key-value ─────────────
                if design:
                    await conn.executemany("""
                        INSERT INTO mpu_hw_design
                            (project_id, version, mpu_name, param_key, param_value)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (project_id, version, mpu_name, param_key)
                        DO UPDATE SET param_value = EXCLUDED.param_value
                    """, [
                        (project_id, version, mpu_name, k, str(v))
                        for k, v in design.items()
                    ])

                # ── Bulk-insert hw.integration fields ─────────────────────────
                if integration:
                    await conn.executemany("""
                        INSERT INTO mpu_hw_integration
                            (project_id, version, mpu_name, param_key, param_value)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (project_id, version, mpu_name, param_key)
                        DO UPDATE SET param_value = EXCLUDED.param_value
                    """, [
                        (project_id, version, mpu_name, k, str(v))
                        for k, v in integration.items()
                    ])

        # ── Update Redis for this MPU ─────────────────────────────────────────
        await self._cache_single_mpu(project_id, version, mpu_name, design, integration)
        logger.info("Loaded MPU: %s / chip=%s / v=%s", mpu_name, project_id, version)

    async def _cache_single_mpu(
        self,
        pid: int, ver: str, mpu: str,
        design: dict, integration: dict,
    ) -> None:
        """Write all Redis keys for one MPU."""
        pipe = self._redis.pipeline(transaction=False)

        num_rg     = design.get("NUM_RES_GRP", "0")
        xpress     = "1" if design.get("XPRESSCFG_EN", "0") != "0" else "0"
        ff_address = design.get("FF_ADDRESS", "")
        num_qad    = design.get("NUM_QAD", "0")

        # Exact field keys
        pipe.set(K.mpu_rg_count(pid, ver, mpu),  str(num_rg))
        pipe.set(K.mpu_xpresscfg(pid, ver, mpu), xpress)
        pipe.set(K.mpu_ff_address(pid, ver, mpu), ff_address)
        pipe.set(K.mpu_num_qad(pid, ver, mpu),   str(num_qad))

        # Full metadata blob for "show details" queries
        metadata = {
            "mpu_name":          mpu,
            "project_id":        pid,
            "version":           ver,
            "ff_address":        ff_address,
            "xpu4_revision":     f"{design.get('XPU4_REV:MAJOR','?')}."
                                 f"{design.get('XPU4_REV:MINOR','?')}."
                                 f"{design.get('XPU4_REV:STEP','?')}",
            "num_res_grp":       num_rg,
            "num_qad":           num_qad,
            "xpresscfg_en":      xpress == "1",
            "xpresscfg_multidie":design.get("XPRESSCFG_MULTIDIE", "0") != "0",
            "xpu_type":          design.get("XPU_TYPE"),
            "input_msb":         integration.get("InputMSB"),
            "idr0": {
                "nRG":                    design.get("XPU4_IDR0:nRG"),
                "BLED":                   design.get("XPU4_IDR0:BLED"),
                "CLIENT_HALTREQACK_EN":   design.get("XPU4_IDR0:CLIENT_HALTREQACK_EN"),
                "CLIENT_PIPELINE_EN":     design.get("XPU4_IDR0:CLIENT_PIPELINE_EN"),
                "xpressCfgMultiDie":      design.get("XPU4_IDR0:xpressCfgMultiDie"),
                "xpressCfgEn":            design.get("XPU4_IDR0:xpressCfgEn"),
                "XPU_TYPE":               design.get("XPU4_IDR0:XPU_TYPE"),
            },
            "idr1": {
                "CLIENT_ADDR_WIDTH":  design.get("XPU4_IDR1:CLIENT_ADDR_WIDTH"),
                "CONFIG_ADDR_WIDTH":  design.get("XPU4_IDR1:CONFIG_ADDR_WIDTH"),
                "ADDR_MSB":           design.get("XPU4_IDR1:ADDR_MSB"),
                "ADDR_LSB":           design.get("XPU4_IDR1:ADDR_LSB"),
            },
            "idr2": {
                "SyncModeEn":       design.get("XPU4_IDR2:SyncModeEn"),
                "ParityEn":         design.get("XPU4_IDR2:ParityEn"),
                "useQsiCfgIntf":    design.get("XPU4_IDR2:useQsiCfgIntf"),
                "useQsiClientIntf": design.get("XPU4_IDR2:useQsiClientIntf"),
                "useAhbWrapper":    design.get("XPU4_IDR2:useAhbWrapper"),
                "useLegacyIntf":    design.get("XPU4_IDR2:useLegacyIntf"),
                "nQAD":             design.get("XPU4_IDR2:nQAD"),
            },
        }
        pipe.set(K.mpu_metadata(pid, ver, mpu), json.dumps(metadata))

        await pipe.execute()
        
# ─────────────────────────────────────────────────────────────────────────
    # CACHE WARMING — called once at app startup
    # ─────────────────────────────────────────────────────────────────────────
    async def warm_cache(self) -> dict:
        """
        Load all static config from PostgreSQL into Redis.
        After this, agents never touch PostgreSQL at runtime.
        """
        pipe = self._redis.pipeline(transaction=False)
        projects_loaded = mpu_loaded = 0

        # ── Projects ──────────────────────────────────────────────────────────
        projects = await self._pg.fetch(
            "SELECT project_id, project_name FROM projects"
        )
        for p in projects:
            pipe.set(K.project_by_name(p["project_name"]), str(p["project_id"]))
            pipe.set(K.project_by_id(p["project_id"]), p["project_name"])
            projects_loaded += 1

        # ── Versions per project ──────────────────────────────────────────────
        versions = await self._pg.fetch("""
            SELECT project_id, array_agg(version ORDER BY version) AS versions
            FROM project_versions WHERE is_active = TRUE
            GROUP BY project_id
        """)
        for v in versions:
            pipe.set(K.project_versions(v["project_id"]), json.dumps(v["versions"]))

        # ── MPU configs ───────────────────────────────────────────────────────
        mpus = await self._pg.fetch("""
            SELECT project_id, version, mpu_name,
                   ff_address, num_res_grp, num_qad,
                   xpresscfg_en, xpresscfg_multidie, xpu_type,
                   xpu4_rev_major, xpu4_rev_minor, xpu4_rev_step,
                   input_msb,
                   COUNT(*) OVER (PARTITION BY project_id, version) AS version_mpu_count
            FROM mpu_configs
            WHERE is_active = TRUE
            ORDER BY project_id, version, mpu_name
        """)

        # Group for list keys
        version_groups: dict = {}
        for m in mpus:
            pid, ver, mpu = m["project_id"], m["version"], m["mpu_name"]

            # Exact field keys
            pipe.set(K.mpu_rg_count(pid, ver, mpu),  str(m["num_res_grp"] or 0))
            pipe.set(K.mpu_xpresscfg(pid, ver, mpu), "1" if m["xpresscfg_en"] else "0")
            pipe.set(K.mpu_ff_address(pid, ver, mpu), m["ff_address"] or "")
            pipe.set(K.mpu_num_qad(pid, ver, mpu),   str(m["num_qad"] or 0))
            pipe.set(K.mpu_count(pid, ver),           str(m["version_mpu_count"]))

            # Metadata blob
            meta = {
                "mpu_name":    mpu,
                "project_id":  pid,
                "version":     ver,
                "ff_address":  m["ff_address"],
                "xpu4_revision": f"{m['xpu4_rev_major']}.{m['xpu4_rev_minor']}.{m['xpu4_rev_step']}",
                "num_res_grp": m["num_res_grp"],
                "num_qad":     m["num_qad"],
                "xpresscfg_en": m["xpresscfg_en"],
                "xpresscfg_multidie": m["xpresscfg_multidie"],
                "xpu_type":    m["xpu_type"],
                "input_msb":   m["input_msb"],
            }
            pipe.set(K.mpu_metadata(pid, ver, mpu), json.dumps(meta))

            # Accumulate for list key
            vk = (pid, ver)
            if vk not in version_groups:
                version_groups[vk] = []
            version_groups[vk].append({
                "mpu_name":     mpu,
                "ff_address":   m["ff_address"],
                "num_res_grp":  m["num_res_grp"],
                "xpresscfg_en": m["xpresscfg_en"],
            })
            mpu_loaded += 1

        for (pid, ver), mpu_list in version_groups.items():
            pipe.set(K.mpu_list(pid, ver), json.dumps(mpu_list))

        await pipe.execute()
        logger.info("Cache warm: %d projects, %d MPUs", projects_loaded, mpu_loaded)
        return {"projects": projects_loaded, "mpus": mpu_loaded}

    # ─────────────────────────────────────────────────────────────────────────
    # READ — agents call these at runtime (Redis first, PG fallback)
    # ─────────────────────────────────────────────────────────────────────────
    async def get_mpu_rg_count(self, pid: int, ver: str, mpu: str) -> Optional[int]:
        val = await self._redis.get(K.mpu_rg_count(pid, ver, mpu))
        if val is not None:
            return int(val)
        row = await self._pg.fetchrow(
            "SELECT num_res_grp FROM mpu_configs WHERE project_id=$1 AND version=$2 AND mpu_name=$3",
            pid, ver, mpu)
        if row:
            await self._redis.set(K.mpu_rg_count(pid, ver, mpu), str(row["num_res_grp"]))
            return row["num_res_grp"]
        return None

    async def get_xpresscfg_enabled(self, pid: int, ver: str, mpu: str) -> Optional[bool]:
        val = await self._redis.get(K.mpu_xpresscfg(pid, ver, mpu))
        if val is not None:
            return val == "1"
        row = await self._pg.fetchrow(
            "SELECT xpresscfg_en FROM mpu_configs WHERE project_id=$1 AND version=$2 AND mpu_name=$3",
            pid, ver, mpu)
        if row:
            await self._redis.set(K.mpu_xpresscfg(pid, ver, mpu), "1" if row["xpresscfg_en"] else "0")
            return row["xpresscfg_en"]
        return None

    async def get_mpu_metadata(self, pid: int, ver: str, mpu: str) -> Optional[dict]:
        """Full MPU detail — for 'show me details for XPU X' queries."""
        cached = await self._redis.get(K.mpu_metadata(pid, ver, mpu))
        if cached:
            return json.loads(cached)
        # Full join from PostgreSQL including IDR register fields
        design_rows = await self._pg.fetch(
            "SELECT param_key, param_value FROM mpu_hw_design WHERE project_id=$1 AND version=$2 AND mpu_name=$3",
            pid, ver, mpu)
        integ_rows = await self._pg.fetch(
            "SELECT param_key, param_value FROM mpu_hw_integration WHERE project_id=$1 AND version=$2 AND mpu_name=$3",
            pid, ver, mpu)
        if design_rows:
            result = {
                "mpu_name":   mpu,
                "project_id": pid,
                "version":    ver,
                "hw": {
                    "design":      {r["param_key"]: r["param_value"] for r in design_rows},
                    "integration": {r["param_key"]: r["param_value"] for r in integ_rows},
                }
            }
            await self._redis.set(K.mpu_metadata(pid, ver, mpu), json.dumps(result))
            return result
        return None

    async def list_mpus(self, pid: int, ver: str) -> List[dict]:
        """List all MPUs for a project+version."""
        cached = await self._redis.get(K.mpu_list(pid, ver))
        if cached:
            return json.loads(cached)
        rows = await self._pg.fetch(
            "SELECT mpu_name, ff_address, num_res_grp, xpresscfg_en FROM mpu_configs "
            "WHERE project_id=$1 AND version=$2 AND is_active=TRUE ORDER BY mpu_name",
            pid, ver)
        result = [dict(r) for r in rows]
        if result:
            await self._redis.set(K.mpu_list(pid, ver), json.dumps(result))
        return result

    async def find_mpu_by_address(self, pid: int, ver: str, address: int) -> Optional[dict]:
        """Which MPU contains this address? SQL BETWEEN — cannot be done in Redis."""
        row = await self._pg.fetchrow("""
            SELECT mpu_name, ff_address, num_res_grp, xpresscfg_en
            FROM   mpu_configs
            WHERE  project_id    = $1
            AND    version       = $2
            AND    ff_address_int <= $3
            AND    ff_address_int + (num_res_grp * 4096) >= $3
            AND    is_active     = TRUE
            LIMIT  1
        """, pid, ver, address)
        return dict(row) if row else None

    async def find_mpus_with_xpresscfg(self, pid: int, ver: str) -> List[dict]:
        """List all MPUs that have xpresscfg_en=TRUE."""
        rows = await self._pg.fetch("""
            SELECT mpu_name, ff_address, num_res_grp
            FROM   mpu_configs
            WHERE  project_id  = $1
            AND    version     = $2
            AND    xpresscfg_en = TRUE
            AND    is_active   = TRUE
            ORDER  BY mpu_name
        """, pid, ver)
        return [dict(r) for r in rows]

    async def close(self):
        await self._pg.close()


