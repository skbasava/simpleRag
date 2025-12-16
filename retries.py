import time
import logging

def retry(fn, retries=3, base_delay=1, label="operation"):
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:
            logging.warning(
                f"[RETRY] {label} failed (attempt {attempt}/{retries}): {e}"
            )
            if attempt == retries:
                raise
            time.sleep(base_delay * (2 ** (attempt - 1)))
            
            
class IngestionProgressRepo:
    def __init__(self, pg):
        self.pg = pg

    def get(self, xml_path):
        sql = """
        SELECT status, last_chunk_index
        FROM ingestion_progress
        WHERE xml_path = %s
        """
        self.pg.cursor.execute(sql, (xml_path,))
        return self.pg.cursor.fetchone()

    def upsert(self, xml_path, status, last_chunk=-1, error=None):
        sql = """
        INSERT INTO ingestion_progress (xml_path, status, last_chunk_index, error)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (xml_path)
        DO UPDATE SET
            status = EXCLUDED.status,
            last_chunk_index = EXCLUDED.last_chunk_index,
            error = EXCLUDED.error,
            updated_at = now()
        """
        self.pg.cursor.execute(sql, (xml_path, status, last_chunk, error))
        self.pg.conn.commit()

    def update_chunk(self, xml_path, chunk_index):
        sql = """
        UPDATE ingestion_progress
        SET last_chunk_index = %s, updated_at = now()
        WHERE xml_path = %s
        """
        self.pg.cursor.execute(sql, (chunk_index, xml_path))
        self.pg.conn.commit()
        
        
CREATE TABLE IF NOT EXISTS ingestion_progress (
    xml_path TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'IN_PROGRESS', 'DONE', 'FAILED')
    ),
    last_chunk_index INT NOT NULL DEFAULT -1,
    error TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

import glob
import logging

def ingest_all(xml_dir):
    xml_files = sorted(glob.glob(f"{xml_dir}/*.xml"))

    pg = pgConnect()
    pg.pg_connect()

    weaviate = WeaviateClient()
    progress = IngestionProgressRepo(pg)

    for xml_path in xml_files:
        ingest_one_file(xml_path, pg, weaviate, progress)

    pg.pg_shutdown()
    weaviate.close()

def ingest_one_file(xml_path, pg, wv, progress):
    logging.info(f"[INGEST] Processing {xml_path}")

    row = progress.get(xml_path)

    if row:
        status, last_chunk = row
        if status == "DONE":
            logging.info(f"[SKIP] {xml_path} already DONE")
            return
    else:
        progress.upsert(xml_path, "PENDING")

    progress.upsert(xml_path, "IN_PROGRESS")

    try:
        ingest_chunks(xml_path, pg, wv, progress)
        progress.upsert(xml_path, "DONE")
        logging.info(f"[DONE] {xml_path}")

    except Exception as e:
        logging.exception(f"[FAILED] {xml_path}")
        progress.upsert(xml_path, "FAILED", error=str(e))

def ingest_chunks(xml_path, pg, wv, progress):
    chunks = parse_xml_into_chunks(xml_path)

    row = progress.get(xml_path)
    last_chunk = row[1] if row else -1

    for idx, chunk in enumerate(chunks):
        if idx <= last_chunk:
            continue  # ✅ RESUME HERE

        logging.info(f"[CHUNK] {xml_path} -> {idx}")

        retry(
            lambda: ingest_single_chunk(chunk, pg, wv),
            retries=3,
            label=f"chunk {idx}"
        )

        progress.update_chunk(xml_path, idx)
def ingest_single_chunk(chunk, pg, wv):
    # 1. Insert metadata + vector_id into Postgres
    vector_id = retry(
        lambda: pg.insert_chunk(chunk),
        label="postgres insert"
    )

    # 2. Insert vector into Weaviate
    retry(
        lambda: wv.insert_vector(
            vector=chunk["vector"],
            meta=chunk["meta"],
            vid=str(vector_id)
        ),
        label="weaviate insert"
    )
