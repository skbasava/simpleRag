CREATE TABLE xml_chunks (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1024),  -- pgvector column
    chunk_id TEXT NOT NULL,
    parent_path TEXT,
    attributes JSONB,
    chunk_type TEXT,
    token_count INTEGER,
    sequence_number INTEGER,
    total_chunks INTEGER,
    source_file TEXT,
    created_at TIMESTAMP,
    metadata JSONB
);

-- Indexes for performance
CREATE INDEX ON xml_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON xml_chunks(source_file);
CREATE INDEX ON xml_chunks(chunk_type);
CREATE INDEX ON xml_chunks USING gin(metadata);
