#!/bin/sh
# Simple restore script for Postgres running in docker-compose
# Usage: ./restore.sh /path/to/backup.sql
if [ -z "$1" ]; then
  echo "Usage: $0 /path/to/backup.sql"
  exit 1
fi
BACKUP_FILE="$1"
if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE"
  exit 1
fi
echo "Restoring from $BACKUP_FILE..."
# Drop and recreate DB in container, then restore
docker exec medqueue-db psql -U medqueue -c "DROP DATABASE medqueue;" 2>/dev/null || true
docker exec medqueue-db psql -U medqueue -c "CREATE DATABASE medqueue;" || { echo "Failed to create DB"; exit 1; }
docker exec -i medqueue-db psql -U medqueue -d medqueue < "$BACKUP_FILE"
if [ $? -eq 0 ]; then
  echo "Restore completed successfully"
  exit 0
else
  echo "Restore failed"
  exit 1
fi
