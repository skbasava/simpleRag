-- =====================================================
-- POLICY CHUNKS (SOURCE OF TRUTH)
-- =====================================================

CREATE TABLE IF NOT EXISTS policy_chunks (
    id BIGSERIAL PRIMARY KEY,

    -- -------------------------
    -- Identity & versioning
    -- -------------------------
    project TEXT NOT NULL,
    version TEXT NOT NULL,

    mpu_name TEXT NOT NULL,
    rg_index INT NOT NULL,

    -- Profile handling
    -- Empty profile in XML normalized to 'TZ'
    profile TEXT NOT NULL DEFAULT 'TZ',

    -- -------------------------
    -- Address range (AUDIT SAFE)
    -- Stored as HEX STRING (do NOT convert to INT)
    -- -------------------------
    start_hex TEXT NOT NULL,
    end_hex   TEXT NOT NULL,

    -- -------------------------
    -- Chunking
    -- -------------------------
    chunk_index INT NOT NULL,
    chunk_text  TEXT NOT NULL,

    -- -------------------------
    -- Vector linkage
    -- -------------------------
    weaviate_id TEXT UNIQUE,

    -- -------------------------
    -- Metadata
    -- -------------------------
    created_at TIMESTAMP NOT NULL DEFAULT now(),

    -- -------------------------
    -- Idempotency guarantee
    -- -------------------------
    UNIQUE (
        project,
        version,
        mpu_name,
        rg_index,
        profile,
        chunk_index
    )
);

-- -------------------------
-- HOT PATH INDEXES
-- -------------------------

CREATE INDEX IF NOT EXISTS idx_policy_project_version
    ON policy_chunks (project, version);

CREATE INDEX IF NOT EXISTS idx_policy_mpu
    ON policy_chunks (mpu_name);

CREATE INDEX IF NOT EXISTS idx_policy_profile
    ON policy_chunks (profile);

CREATE INDEX IF NOT EXISTS idx_policy_rg
    ON policy_chunks (rg_index);



-- =====================================================
-- INGESTION PROGRESS (JOB STATE MACHINE)
-- =====================================================

CREATE TABLE IF NOT EXISTS ingestion_progress (
    xml_path TEXT PRIMARY KEY,

    -- Job state
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'IN_PROGRESS', 'DONE', 'FAILED')
    ),

    -- Resume pointer
    last_chunk_index INT NOT NULL DEFAULT -1,

    -- Error diagnostics
    error TEXT,

    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- -------------------------
-- Progress lookup index
-- -------------------------

CREATE INDEX IF NOT EXISTS idx_ingestion_status
    ON ingestion_progress (status);