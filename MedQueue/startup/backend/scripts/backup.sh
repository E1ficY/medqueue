#!/bin/sh
# Simple backup script for Postgres running in docker-compose
# Usage: ./backup.sh /path/to/output/dir
OUTDIR=${1:-/var/backups}
DATE=$(date +"%Y%m%d_%H%M%S")
FILENAME="medqueue_db_backup_${DATE}.sql"
mkdir -p "$OUTDIR"
# Run pg_dump from host using docker exec
docker exec medqueue-db pg_dump -U medqueue medqueue > "$OUTDIR/$FILENAME"
if [ $? -eq 0 ]; then
  echo "Backup saved to $OUTDIR/$FILENAME"
  exit 0
else
  echo "Backup failed"
  exit 1
fi
