# app/ingestion/state_machine.py

import logging
from app.ingestion.xml_parser import iter_policy_chunks

log = logging.getLogger(__name__)


def ingest_all(pg, weaviate):
    """
    Job-based ingestion entrypoint.
    Safe to restart.
    """

    log.info("[ingest] starting state machine")

    # Example: iterate XMLs from mounted folder
    xml_files = discover_xml_files("/data/policies")

    for xml_path in xml_files:
        ingest_single_xml(pg, weaviate, xml_path)

    log.info("[ingest] state machine completed")


def ingest_single_xml(pg, weaviate, xml_path: str):
    """
    Ingest a single XML file with resume support.
    """

    progress = pg.get_ingestion_progress(xml_path)

    last_chunk = progress["last_chunk_index"] if progress else -1

    log.info(
        "[ingest] xml=%s resume_from_chunk=%s",
        xml_path,
        last_chunk + 1,
    )

    pg.mark_ingestion_in_progress(xml_path)

    for chunk in iter_policy_chunks(xml_path):
        if chunk["chunk_index"] <= last_chunk:
            continue

        # ---- Insert into Postgres (idempotent) ----
        chunk_id = pg.insert_chunk(chunk)
        if not chunk_id:
            continue

        # ---- Vector insert ----
        vector = chunk["embedding"]
        wid = weaviate.insert_vector(
            vector=vector,
            properties={
                "chunk_id": chunk_id,
                "project": chunk["project"],
                "version": chunk["version"],
                "mpu_name": chunk["mpu_name"],
                "profile": chunk["profile"],
                "rg_index": chunk["rg_index"],
                "chunk_text": chunk["chunk_text"],
            },
        )

        pg.update_weaviate_id(chunk_id, wid)
        pg.update_ingestion_progress(xml_path, chunk["chunk_index"])

    pg.mark_ingestion_done(xml_path)
    log.info("[ingest] completed xml=%s")


# ---------------------------
# Helpers
# ---------------------------

def discover_xml_files(root: str):
    import os

    return [
        os.path.join(root, f)
        for f in os.listdir(root)
        if f.endswith(".xml")
    ]