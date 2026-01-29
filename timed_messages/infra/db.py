import os

import psycopg2
import psycopg2.extras


def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to connect to Postgres")
    dsn = database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    conn = psycopg2.connect(dsn)
    psycopg2.extras.register_uuid(conn_or_curs=conn)
    return conn
