
def insert_chunk(cur, row):

    sql = """
        INSERT INTO policy_chunks (
            project, mpu_name, rg_index, profile,
            start_hex, end_hex,
            start_dec, end_dec,
            identity_hash, content_hash,
            chunk_index, chunk_text,
            vector_id, xml_path,
            is_active
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
        ON CONFLICT (identity_hash, chunk_index)
        DO UPDATE SET
            content_hash = EXCLUDED.content_hash,
            chunk_text   = EXCLUDED.chunk_text,
            vector_id    = EXCLUDED.vector_id,
            xml_path     = EXCLUDED.xml_path,
            is_active    = TRUE
        RETURNING id;
    """

    params = (
        row["project"],
        row["mpu_name"],
        row["rg_index"],
        row["profile"],
        row["start_hex"],
        row["end_hex"],
        row["start_dec"],
        row["end_dec"],
        row["identity_hash"],
        row["content_hash"],
        row["chunk_index"],
        row["chunk_text"],
        row["vector_id"],
        row["xml_path"],
    )

    try:
        cur.execute(sql, params)
        new_id = cur.fetchone()
        print(f"[DB] fetch from DB {new_id}")
        return new_id[0] if new_id else None

    except Exception as e:
        print("[DB] ERROR insert_chunk:", e)
        print("ROW Data:", row)
        return None



POSTGRES = {
    "host": "localhost",
    "port": 5432,
    "db": "ragdb",
    "user": "raguser",
    "password": "ragpass"
}

WEAVIATE = {
    "url": "http://localhost:8080",
    "class": "AccessControlPolicy"
}

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

import hashlib, json

def normalize_profile(p):
    return p.strip() if p and p.strip() else "TZ"

def identity_hash(project, mpu, rg, profile, start, end):
    k = f"{project}|{mpu}|{rg}|{profile}|{start}|{end}"
    return hashlib.sha256(k.encode()).hexdigest()

def content_hash(data: dict):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    
import psycopg2, requests
from sentence_transformers import SentenceTransformer
from config import POSTGRES, WEAVIATE, EMBED_MODEL

db = psycopg2.connect(**POSTGRES)
db.autocommit = False
cur = db.cursor()

embedder = SentenceTransformer(EMBED_MODEL)

def chunk_text(text, size=512):
    words = text.split()
    for i in range(0, len(words), size):
        yield i // size, " ".join(words[i:i+size])
        
        
import uuid

def insert_vector(chunk, meta):
    vector = embedder.encode(chunk).tolist()
    vid = str(uuid.uuid4())

    payload = {
        "class": WEAVIATE["class"],
        "id": vid,
        "properties": meta,
        "vector": vector
    }

    r = requests.post(
        f"{WEAVIATE['url']}/v1/objects",
        json=payload
    )
    r.raise_for_status()
    return vid

def deactivate_old(identity):
    cur.execute("""
        UPDATE policy_chunks
        SET is_active = FALSE, updated_at = now()
        WHERE identity_hash = %s AND is_active = TRUE
    """, (identity,))
    
def insert_chunk(row):
    cur.execute("""
        INSERT INTO policy_chunks (
            project, mpu_name, rg_index, profile,
            start_dec, end_dec,
            policy_version,
            identity_hash, content_hash,
            chunk_index, chunk_text,
            vector_id,
            is_active,
            xml_path
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s)
        ON CONFLICT (identity_hash, chunk_index) DO NOTHING
    """, row)
    from lxml import etree

def parse_xml(xml_path):
    tree = etree.parse(xml_path)
    root = tree.getroot()

    project = root.get("project")
    version = root.get("version")

    for mpu in root.findall(".//MPU"):
        mpu_name = mpu.get("name")

        for prtn in mpu.findall(".//PRTn"):
            rg = int(prtn.get("index"))
            profile = normalize_profile(prtn.get("profile"))

            start = int(prtn.get("start"), 16)
            end   = int(prtn.get("end"), 16)

            content = etree.tostring(prtn, encoding="unicode")

            yield {
                "project": project,
                "mpu": mpu_name,
                "rg": rg,
                "profile": profile,
                "start": start,
                "end": end,
                "policy_version": version,
                "content": content
            }

def ingest(xml_path):
    print("Parsing:", xml_path)

    for policy in parse_xml(xml_path):
        meta = {
            "project": policy["project"],
            "mpu": policy["mpu"],
            "rg": policy["rg"],
            "profile": policy["profile"],
            "start": policy["start"],
            "end": policy["end"],
            "version": policy["policy_version"]
        }

        identity = identity_hash(**meta)
        content_h = content_hash(policy)

        # Deactivate old version first
        deactivate_old(identity)

        for idx, chunk in chunk_text(policy["content"]):
            vector_id = insert_vector(chunk, meta)

            row = (
                meta["project"],
                meta["mpu"],
                meta["rg"],
                meta["profile"],
                meta["start"],
                meta["end"],
                meta["version"],
                identity,
                content_h,
                idx,
                chunk,
                vector_id,
                xml_path
            )

            insert_chunk(row)

    db.commit()
    print("✅ Ingestion completed successfully")
    




