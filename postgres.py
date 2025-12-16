import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
import os


class PostgresDriver:
    def __init__(self):
        self.pool = SimpleConnectionPool(
            minconn=1,
            maxconn=10,  # scale with load
            dsn=os.environ["PG_DSN"],
        )

    @contextmanager
    def cursor(self):
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    # --------- writes ---------

    def insert_chunk(self, chunk: dict) -> int:
        sql = """
        INSERT INTO policy_chunks (
            project, version, mpu_name, rg_index, profile,
            start_hex, end_hex,
            chunk_index, chunk_text
        )
        VALUES (
            %(project)s, %(version)s, %(mpu_name)s, %(rg_index)s, %(profile)s,
            %(start_hex)s, %(end_hex)s,
            %(chunk_index)s, %(chunk_text)s
        )
        ON CONFLICT DO NOTHING
        RETURNING id
        """

        with self.cursor() as cur:
            cur.execute(sql, chunk)
            row = cur.fetchone()
            return row["id"] if row else None

    def update_weaviate_id(self, chunk_id: int, wid: str):
        with self.cursor() as cur:
            cur.execute(
                "UPDATE policy_chunks SET weaviate_id=%s WHERE id=%s",
                (wid, chunk_id),
            )

    # --------- reads ---------

    def fetch_chunks(self, filters: dict):
        clauses = []
        params = {}

        for k, v in filters.items():
            clauses.append(f"{k} = %({k})s")
            params[k] = v

        where = " AND ".join(clauses)
        sql = f"SELECT * FROM policy_chunks WHERE {where}"

        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()