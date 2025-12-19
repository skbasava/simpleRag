import psycopg2
import random
import os

VECTOR_DIM = 1024

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "ragdb"),
    "user": os.getenv("DB_USER", "raguser"),
    "password": os.getenv("DB_PASSWORD", "ragpassword"),
}

def fake_embedding(dim=VECTOR_DIM):
    return [random.random() for _ in range(dim)]

def main():
    print("🔌 Connecting to Postgres...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT extname FROM pg_extension WHERE extname='vector';")
    assert cur.fetchone(), "pgvector extension missing"
    print("✅ pgvector installed")

    embedding = fake_embedding()

    cur.execute(
        """
        INSERT INTO xml_chunks (project, version, raw_text, chunk_hash, embedding)
        VALUES (%s, %s, %s, %s, %s::vector)
        RETURNING id;
        """,
        (
            "TEST_PROJECT",
            "1.0",
            "pgvector docker validation chunk",
            "hash_test_001",
            embedding,
        )
    )
    chunk_id = cur.fetchone()[0]
    conn.commit()
    print(f"✅ Inserted chunk id={chunk_id}")

    cur.execute(
        "SELECT length(embedding) FROM xml_chunks WHERE id=%s;",
        (chunk_id,)
    )
    dim = cur.fetchone()[0]
    assert dim == VECTOR_DIM, f"Vector dim mismatch: {dim}"
    print(f"✅ Vector dimension = {dim}")

    cur.execute(
        """
        SELECT id, embedding <-> %s::vector AS distance
        FROM xml_chunks
        ORDER BY distance
        LIMIT 1;
        """,
        (embedding,)
    )
    rid, dist = cur.fetchone()
    print(f"✅ Nearest id={rid}, distance={dist}")

    cur.execute("DELETE FROM xml_chunks WHERE id=%s;", (chunk_id,))
    conn.commit()
    print("🧹 Cleanup done")

    cur.close()
    conn.close()
    print("\n🎉 pgvector Docker validation SUCCESS")

if __name__ == "__main__":
    main()