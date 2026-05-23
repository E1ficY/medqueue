#!/usr/bin/env bash
set -euo pipefail

# prod_update.sh
# Safe, repeatable helper to update production code, back up the Postgres DB,
# rebuild the Docker Compose stack and run basic checks.
#
# Usage: sudo ./prod_update.sh [branch] [backup-dir]
# Example: sudo ./prod_update.sh main /tmp

BRANCH=${1:-main}
BACKUP_DIR=${2:-/tmp}

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"

echo "Project: $PROJECT_ROOT"
echo "Compose file: $COMPOSE_FILE"
echo "Branch: $BRANCH"
echo "Backup dir: $BACKUP_DIR"

if [[ $(id -u) -ne 0 ]]; then
  echo "Warning: it's recommended to run this as root or a user with docker access. Continuing..."
fi

# detect compose command
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif docker-compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "Error: neither 'docker compose' nor 'docker-compose' found in PATH" >&2
  exit 1
fi

cd "$PROJECT_ROOT"

echo "Fetching latest code and resetting to origin/$BRANCH"
git fetch --all --prune
git reset --hard "origin/$BRANCH"

echo "Locating DB container for service 'db' via compose..."
DB_CONTAINER=$($COMPOSE_CMD -f "$COMPOSE_FILE" ps -q db 2>/dev/null || true)
if [[ -z "$DB_CONTAINER" ]]; then
  echo "Compose service 'db' has no running container. Falling back to docker ps search for postgres image."
  DB_CONTAINER=$(docker ps --filter "ancestor=postgres" --format "{{.Names}}" | head -n1 || true)
fi

if [[ -z "$DB_CONTAINER" ]]; then
  echo "Error: Could not find Postgres container. Start the stack or ensure the service is named 'db' in compose." >&2
  exit 1
fi

TIMESTAMP=$(date +%F_%H%M%S)
BACKUP_NAME="medqueue_db_backup_${TIMESTAMP}.sql"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

echo "Creating DB dump from container: $DB_CONTAINER -> $BACKUP_PATH"
docker exec -i "$DB_CONTAINER" pg_dump -U medqueue medqueue > "$BACKUP_PATH"
gzip -f "$BACKUP_PATH"
BACKUP_PATH_GZ="$BACKUP_PATH.gz"

echo "Backup created: $BACKUP_PATH_GZ"

echo "Pulling images (if available) and rebuilding services"
$COMPOSE_CMD -f "$COMPOSE_FILE" pull --ignore-pull-failures || true
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d --build

echo "Waiting 3s for services to start..."
sleep 3

echo "Showing last 200 lines of backend and nginx logs"
$COMPOSE_CMD -f "$COMPOSE_FILE" logs --tail 200 backend nginx || true

echo "Checking API endpoint (local on server)"
if command -v curl >/dev/null 2>&1; then
  curl -sS -k --max-time 10 'https://localhost/api/doctors/?page=1' | sed -n '1,120p' || echo "curl failed or timed out"
else
  echo "curl not available; skipping HTTP check"
fi

echo
echo "Done. Backup file on server: $BACKUP_PATH_GZ"
echo "To download backup to your machine:"
echo "  scp root@<server>:$BACKUP_PATH_GZ /local/path/"
echo
echo "If you want me to generate a one-shot encoding-fix workflow, reply and I will provide the commands to run on a restored copy of the SQL dump (do NOT run without verifying the dump)."

exit 0
