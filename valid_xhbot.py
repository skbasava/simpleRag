import psycopg2
import random

# ---------------- CONFIG ----------------
DB_CONFIG = {
    "host": "localhost",      # or service name if docker
    "port": 5432,
    "dbname": "ragdb",
    "user": "raguser",
    "password": "ragpassword",
}

VECTOR_DIM = 1024
# ----------------------------------------


def fake_embedding(dim=VECTOR_DIM):
    """Generate a dummy embedding for validation"""
    return [random.random() for _ in range(dim)]


def main():
    print("Connecting to Postgres...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # 1️⃣ Validate pgvector extension
    cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
    assert cur.fetchone(), "❌ pgvector extension NOT installed"
    print("✔ pgvector extension present")

    # 2️⃣ Validate table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'xml_chunks'
        );
    """)
    assert cur.fetchone()[0], "❌ xml_chunks table missing"
    print("✔ xml_chunks table exists")

    # 3️⃣ Insert test chunk
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
            "This is a pgvector validation chunk",
            "test_hash_123",
            embedding,
        )
    )

    chunk_id = cur.fetchone()[0]
    conn.commit()
    print(f"✔ Inserted test chunk id={chunk_id}")

    # 4️⃣ Validate vector dimension
    cur.execute(
        "SELECT length(embedding) FROM xml_chunks WHERE id = %s;",
        (chunk_id,)
    )
    dim = cur.fetchone()[0]
    assert dim == VECTOR_DIM, f"❌ Vector dim {dim}, expected {VECTOR_DIM}"
    print(f"✔ Vector dimension = {dim}")

    # 5️⃣ Similarity search (self match)
    cur.execute(
        """
        SELECT id, embedding <-> %s::vector AS distance
        FROM xml_chunks
        ORDER BY distance
        LIMIT 1;
        """,
        (embedding,)
    )

    result_id, distance = cur.fetchone()
    print(f"✔ Nearest chunk id={result_id}, distance={distance}")

    assert distance < 1e-6, "❌ Self-distance is not ~0"
    print("✔ Distance sanity check passed")

    # 6️⃣ Cleanup
    cur.execute("DELETE FROM xml_chunks WHERE id = %s;", (chunk_id,))
    conn.commit()
    print("✔ Cleanup complete")

    cur.close()
    conn.close()
    print("\n✅ pgvector validation SUCCESS")


if __name__ == "__main__":
    main()