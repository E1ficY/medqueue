#!/usr/bin/env bash
set -euo pipefail

# encoding_fix_workflow.sh
# Lightweight, destructive-safe helper to inspect a SQL dump and produce
# a CP866 -> UTF-8 converted SQL file for testing.
#
# Usage: ./encoding_fix_workflow.sh /path/to/medqueue_db_backup.sql.gz /path/to/workdir

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/dump.sql.gz [workdir]"
  exit 2
fi

INPUT_GZ=$1
WORKDIR=${2:-./encoding_fix_workdir}

mkdir -p "$WORKDIR"
cp -v "$INPUT_GZ" "$WORKDIR/"
cd "$WORKDIR"

ORIG_GZ=$(basename "$INPUT_GZ")
echo "Working copy: $WORKDIR/$ORIG_GZ"

if ! command -v gunzip >/dev/null 2>&1; then
  echo "Error: gunzip is required" >&2
  exit 1
fi
if ! command -v iconv >/dev/null 2>&1; then
  echo "Error: iconv is required" >&2
  exit 1
fi

gunzip -kf "$ORIG_GZ"
SQL_FILE="${ORIG_GZ%.gz}"

echo "Checking if dump is valid UTF-8..."
if iconv -f UTF-8 -t UTF-8 "$SQL_FILE" > /dev/null 2>&1; then
  echo "Dump appears to be valid UTF-8. No conversion needed."
  echo "Sample (first 80 lines):"
  head -n 80 "$SQL_FILE"
  exit 0
fi

echo "Dump is not valid UTF-8. Attempting conversion from CP866 -> UTF-8..."
CONVERTED_SQL="${SQL_FILE%.sql}.converted.utf8.sql"
iconv -f CP866 -t UTF-8 "$SQL_FILE" -o "$CONVERTED_SQL" || {
  echo "iconv failed to convert using CP866" >&2
  exit 1
}

echo
echo "--- Original sample (first 40 lines) ---"
head -n 40 "$SQL_FILE" || true
echo
echo "--- Converted sample (first 40 lines) ---"
head -n 40 "$CONVERTED_SQL" || true

echo
echo "Conversion complete. Converted file: $WORKDIR/$CONVERTED_SQL"
echo
echo "Next safe testing steps (recommended):"
echo "1) Create a disposable Postgres container or use a staging DB. Example:"
echo "   docker run --name tmp-pg -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=testdb -d postgres:15-alpine"
echo "2) Restore converted dump into that DB (adjust psql user/db):"
echo "   gunzip -c $ORIG_GZ | docker exec -i tmp-pg psql -U postgres -d testdb   # if original is gz"
echo "   # or restore converted (already UTF-8):"
echo "   docker exec -i tmp-pg psql -U postgres -d testdb < $CONVERTED_SQL"
echo "3) Manually inspect records in the test DB with psql or a tool."
echo
echo "IMPORTANT: Do NOT restore 'converted' into production until fully validated and you have a verified backup."

exit 0
