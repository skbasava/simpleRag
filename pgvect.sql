-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Main table for XML chunks
CREATE TABLE IF NOT EXISTS xml_chunks (
    id SERIAL PRIMARY KEY,

    project TEXT NOT NULL,
    version TEXT NOT NULL,

    raw_text TEXT NOT NULL,

    chunk_hash TEXT UNIQUE NOT NULL,

    embedding VECTOR(768),  -- adjust dimension to your embedding model

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector similarity index
CREATE INDEX IF NOT EXISTS idx_xml_chunks_embedding
ON xml_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Metadata indexes
CREATE INDEX IF NOT EXISTS idx_xml_chunks_project
ON xml_chunks (project);

CREATE INDEX IF NOT EXISTS idx_xml_chunks_version
ON xml_chunks (version);

CREATE INDEX IF NOT EXISTS idx_xml_chunks_project_version
ON xml_chunks (project, version);