CREATE TABLE policy_chunks (
    id              BIGSERIAL PRIMARY KEY,

    project         TEXT NOT NULL,
    mpu_name        TEXT NOT NULL,
    rg_index        INT  NOT NULL,
    profile         TEXT NOT NULL,

    start_hex       TEXT NOT NULL,
    end_hex         TEXT NOT NULL,
    start_dec       BIGINT NOT NULL,
    end_dec         BIGINT NOT NULL,

    rdomains        TEXT[] NOT NULL,
    wdomains        TEXT[] NOT NULL,

    chunk_index     INT NOT NULL,
    chunk_text      TEXT NOT NULL,

    identity_hash   TEXT NOT NULL,
    content_hash    TEXT NOT NULL,

    vector_id       TEXT,

    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT now(),

    UNIQUE(identity_hash, chunk_index)
);