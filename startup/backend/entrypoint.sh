#!/bin/sh
set -e

# Wait for the database to become available before running migrations.
MAX_DB_ATTEMPTS="${DB_CONNECT_MAX_ATTEMPTS:-30}"
DB_RETRY_DELAY="${DB_CONNECT_RETRY_DELAY:-2}"
DB_ATTEMPT=1

until python manage.py migrate --noinput; do
  if [ "$DB_ATTEMPT" -ge "$MAX_DB_ATTEMPTS" ]; then
    echo "[entrypoint] Database is still unavailable after ${MAX_DB_ATTEMPTS} attempts."
    exit 1
  fi

  echo "[entrypoint] Database is not ready yet (attempt ${DB_ATTEMPT}/${MAX_DB_ATTEMPTS}); retrying in ${DB_RETRY_DELAY}s..."
  DB_ATTEMPT=$((DB_ATTEMPT + 1))
  sleep ${DB_RETRY_DELAY}
done

python manage.py collectstatic --noinput

exec "$@"
