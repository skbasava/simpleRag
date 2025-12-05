import os
import glob
import uuid
import hashlib
from typing import Optional, Dict, Any, List

import psycopg2
import weaviate
from lxml import etree


# -----------------------------
# CONFIG FROM ENV
# -----------------------------

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_DB = os.getenv("PG_DB", "ragdb")
PG_USER = os.getenv("PG_USER", "raguser")
PG_PASSWORD = os.getenv("PG_PASSWORD", "ragpass")

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
WEAVIATE_CLASS = "AccessControlPolicy"

POLICY_VERSION = os.getenv("POLICY_VERSION", "v1.0")

POLICY_ROOT = "./policies"   # host directory


# -----------------------------
# CONNECTIONS
# -----------------------------

pg = psycopg2.connect(
    host=PG_HOST,
    dbname=PG_DB,
    user=PG_USER,
    password=PG_PASSWORD
)
pg.autocommit = True

wv = weaviate.Client(WEAVIATE_URL)


# -----------------------------
# UTILS
# -----------------------------

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hex_to_dec(val: Optional[str]):
    if not val:
        return None
    try:
        return int(val, 16)
    except Exception:
        return None


def normalize_list(val: Optional[str]):
    if not val:
        return []
    return [v.strip() for v in val.split(",") if v.strip()]


# -----------------------------
# POSTGRES HELPERS
# -----------------------------

def pg_fetch_one(query: str, params: tuple):
    cur = pg.cursor()
    cur.execute(query, params)
    return cur.fetchone()


def pg_execute(query: str, params: tuple):
    cur = pg.cursor()
    cur.execute(query, params)


# -----------------------------
# WEAVIATE HELPERS
# -----------------------------

def delete_weaviate_vector(chunk_id: str):
    try:
        wv.data_object.delete(chunk_id, WEAVIATE_CLASS)
        print(f"    🗑️  Deleted old vector {chunk_id}")
    except Exception:
        pass


def insert_weaviate_vector(chunk_id: str, obj: Dict[str, Any]):
    wv.data_object.create(
        data_object=obj,
        class_name=WEAVIATE_CLASS,
        uuid=chunk_id
    )


# -----------------------------
# PARSE ONE <PRTn>
# -----------------------------

def parse_prtn(node: etree._Element) -> Dict[str, Any]:
    return {
        "rg_index": int(node.get("index")),
        "profile": node.get("profile"),
        "order": int(node.get("order", "0")),
        "locks": node.get("locks"),
        "confirmed": node.get("confirmed") == "true",
        "start_hex": node.get("start"),
        "end_hex": node.get("end"),
        "rdomains": normalize_list(node.get("rdomains")),
        "wdomains": normalize_list(node.get("wdomains")),
        "rvmids": normalize_list(node.get("rvmids")),
        "wvmids": normalize_list(node.get("wvmids")),
        "raw_xml": etree.tostring(node, pretty_print=True).decode(),
    }


# -----------------------------
# CORE INGESTION LOGIC
# -----------------------------

def ingest_prtn(project: str, mpu_name: str, prtn: Dict[str, Any]):

    xml_hash = sha256(prtn["raw_xml"])
    rg_index = prtn["rg_index"]
    profile  = prtn["profile"]

    # 1️⃣ Look up active logical policy
    row = pg_fetch_one(
        """
        SELECT chunk_id, xml_hash
        FROM policy_chunks
        WHERE project=%s
          AND mpu_name=%s
          AND rg_index=%s
          AND COALESCE(profile,'')=COALESCE(%s,'')
          AND is_active=true
        """,
        (project, mpu_name, rg_index, profile)
    )

    # -----------------------------
    # Case A — First Version
    # -----------------------------
    if not row:
        new_chunk_id = str(uuid.uuid4())
        insert_new_policy(project, mpu_name, prtn, xml_hash, new_chunk_id)
        print(f"    ✅ Inserted RG {rg_index} (ACTIVE)")
        return

    old_chunk_id, old_hash = row

    # -----------------------------
    # Case B — No Change
    # -----------------------------
    if old_hash == xml_hash:
        print(f"    ⏭️  Skipped RG {rg_index} (No change)")
        return

    # -----------------------------
    # Case C — Supersede Old
    # -----------------------------
    print(f"    ♻️  Updated RG {rg_index}")

    pg_execute(
        "UPDATE policy_chunks SET is_active=false WHERE chunk_id=%s",
        (old_chunk_id,)
    )

    delete_weaviate_vector(old_chunk_id)

    new_chunk_id = str(uuid.uuid4())
    insert_new_policy(
        project, mpu_name, prtn, xml_hash, new_chunk_id,
        supersedes=old_chunk_id
    )


def insert_new_policy(
    project: str,
    mpu_name: str,
    prtn: Dict[str, Any],
    xml_hash: str,
    chunk_id: str,
    supersedes: Optional[str] = None
):
    start_dec = hex_to_dec(prtn["start_hex"])
    end_dec   = hex_to_dec(prtn["end_hex"])

    pg_execute(
        """
        INSERT INTO policy_chunks (
            chunk_id, project, branch, file_path, policy_version,
            mpu_name, rg_index, profile,
            start_dec, end_dec, start_hex, end_hex,
            rdomains, wdomains, rvmids, wvmids,
            static, confirmed, enabled,
            raw_xml, xml_hash,
            is_active, supersedes_chunk_id,
            weaviate_object_id
        )
        VALUES (%s,%s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,
                true,%s,
                %s)
        """,
        (
            chunk_id,
            project,
            "main",
            None,
            POLICY_VERSION,
            mpu_name,
            prtn["rg_index"],
            prtn["profile"],
            start_dec,
            end_dec,
            prtn["start_hex"],
            prtn["end_hex"],
            prtn["rdomains"],
            prtn["wdomains"],
            prtn["rvmids"],
            prtn["wvmids"],
            False,
            prtn["confirmed"],
            True,
            prtn["raw_xml"],
            xml_hash,
            supersedes,
            chunk_id,    # same ID for Weaviate
        )
    )

    chunk_text = (
        f"MPU: {mpu_name}\n"
        f"Project: {project}\n"
        f"Profile: {prtn['profile']}\n"
        f"RG Index: {prtn['rg_index']}\n"
        f"Start: {prtn['start_hex']}\n"
        f"End: {prtn['end_hex']}\n"
        f"Read Domains: {','.join(prtn['rdomains'])}\n"
        f"Write Domains: {','.join(prtn['wdomains'])}\n"
    )

    insert_weaviate_vector(
        chunk_id,
        {
            "chunk_text": chunk_text,
            "project": project,
            "mpu_name": mpu_name,
            "rg_index": prtn["rg_index"],
            "profile": prtn["profile"],
        },
    )


# -----------------------------
# PROJECT-LEVEL INGESTION
# -----------------------------

def ingest_project(project_dir: str):
    project = os.path.basename(project_dir)

    print(f"\n[+] Project: {project}")

    for xml_file in glob.glob(os.path.join(project_dir, "*.xml")):
        print(f"    -> Parsing {xml_file}")

        tree = etree.parse(xml_file)
        root = tree.getroot()

        # MPU name is usually in parent node or attribute
        mpu_name = root.get("name") or root.tag

        for prtn_node in root.findall(".//PRTn"):
            prtn = parse_prtn(prtn_node)
            ingest_prtn(project, mpu_name, prtn)


# -----------------------------
# MAIN
# -----------------------------

def main():
    for project_dir in glob.glob(os.path.join(POLICY_ROOT, "*")):
        if os.path.isdir(project_dir):
            ingest_project(project_dir)

    print("\n✅ Ingestion completed successfully")


if __name__ == "__main__":
    main()