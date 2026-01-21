#!/bin/sh
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  if [ -z "${DATABASE_URL:-}" ]; then
    echo "DATABASE_URL is not set; skipping migrations."
  else
    echo "Waiting for database..."
    python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine

url = os.environ.get("DATABASE_URL")
for _ in range(60):
    try:
        engine = create_engine(url)
        with engine.connect():
            pass
        break
    except Exception:
        time.sleep(1)
else:
    print("Database not reachable after 60s", file=sys.stderr)
    sys.exit(1)
PY
    echo "Running migrations..."
    alembic -c /app/timed_messages/alembic.ini upgrade head
  fi
fi

exec "$@"
