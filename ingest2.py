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

def chunk_text(text, size=512):
    words = text.split()
    for i in range(0, len(words), size):
        yield i // size, " ".join(words[i:i+size])

import psycopg2, requests
from sentence_transformers import SentenceTransformer
from config import POSTGRES, WEAVIATE, EMBED_MODEL

db = psycopg2.connect(**POSTGRES)
db.autocommit = False
cur = db.cursor()

embedder = SentenceTransformer(EMBED_MODEL)

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

import sys

if __name__ == "__main__":
    xml_file = sys.argv[1]
    ingest(xml_file)


