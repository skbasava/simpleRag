# app/ingest.py

import logging
from app.db.weaviate import WeaviateDriver
from app.db.weaviate_schema import ensure_schema
from app.db.postgres import PostgresDriver
from app.ingestion.state_machine import ingest_all


logging.basicConfig(level=logging.INFO)


def main():
    logging.info("[ingest] starting ingestion job")

    # ---- Postgres ----
    pg = PostgresDriver()

    # ---- Weaviate ----
    wv = WeaviateDriver()
    ensure_schema(wv.client)

    # ---- Run ingestion ----
    ingest_all(pg, wv)

    logging.info("[ingest] ingestion completed")


if __name__ == "__main__":
    main()