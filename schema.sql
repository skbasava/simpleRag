-- ================================
-- Core Table: policy_chunks
-- ================================

CREATE TABLE IF NOT EXISTS policy_chunks (
    id BIGSERIAL PRIMARY KEY,

    -- Canonical Policy Identity
    project        TEXT NOT NULL,
    mpu_name       TEXT NOT NULL,
    rg_index       INTEGER NOT NULL,
    profile        TEXT NOT NULL DEFAULT 'TZ',

    -- Address Range
    start_dec      BIGINT NOT NULL,
    end_dec        BIGINT NOT NULL,
    start_hex      TEXT,
    end_hex        TEXT,

    -- Versioning & Hashing
    policy_version TEXT NOT NULL,
    identity_hash  TEXT NOT NULL,
    content_hash   TEXT NOT NULL,

    -- Chunking
    chunk_index    INTEGER NOT NULL,
    chunk_text     TEXT NOT NULL,

    -- Vector Mapping
    vector_id      TEXT NOT NULL,
    vector_db      TEXT DEFAULT 'weaviate',

    -- Lifecycle
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    is_propagated  BOOLEAN DEFAULT FALSE,

    -- Traceability
    xml_path       TEXT,
    parent_project TEXT,

    -- Audit
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now()
);

-- ================================
-- CRITICAL CONSTRAINTS
-- ================================

-- Prevent duplicate chunks for same logical policy
CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_chunk
ON policy_chunks(identity_hash, chunk_index);

-- Guarantee only ONE ACTIVE version of a policy
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_identity
ON policy_chunks(identity_hash)
WHERE is_active = TRUE;

-- ================================
-- PERFORMANCE INDEXES
-- ================================

CREATE INDEX IF NOT EXISTS idx_project
ON policy_chunks(project);

CREATE INDEX IF NOT EXISTS idx_project_active
ON policy_chunks(project, is_active);

CREATE INDEX IF NOT EXISTS idx_mpu_rg_profile
ON policy_chunks(mpu_name, rg_index, profile);

CREATE INDEX IF NOT EXISTS idx_range
ON policy_chunks(start_dec, end_dec);

CREATE INDEX IF NOT EXISTS idx_profile_active
ON policy_chunks(profile)
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_content_hash
ON policy_chunks(content_hash);

-- ================================
-- PROJECT HIERARCHY (Propagation)
-- ================================

CREATE TABLE IF NOT EXISTS project_hierarchy (
    parent_project TEXT NOT NULL,
    child_project  TEXT NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (parent_project, child_project)
);

-- ================================
-- INGESTION LOCK (Race Prevention)
-- ================================

CREATE TABLE IF NOT EXISTS ingestion_lock (
    project TEXT PRIMARY KEY,
    locked_at TIMESTAMPTZ DEFAULT now()
);
