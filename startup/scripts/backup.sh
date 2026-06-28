#!/bin/bash
# ─────────────────────────────────────────────────────────────
# MedQueue — Automatic PostgreSQL Backup Script
# Runs daily, keeps last 7 backups, sends result to Telegram
# ─────────────────────────────────────────────────────────────

set -euo pipefail

BACKUP_DIR="/backups"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/medqueue_$TIMESTAMP.sql.gz"
MAX_BACKUPS=7

TELEGRAM_TOKEN="${TELEGRAM_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

mkdir -p "$BACKUP_DIR"

send_telegram() {
    local message="$1"
    if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d parse_mode="HTML" \
            -d text="$message" > /dev/null 2>&1 || true
    fi
}

echo "[$(date)] Starting backup..."

if PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h "$POSTGRES_HOST" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --no-owner \
    --no-acl \
    | gzip > "$BACKUP_FILE"; then

    SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] Backup created: $BACKUP_FILE ($SIZE)"

    # Keep only last MAX_BACKUPS backups
    ls -t "$BACKUP_DIR"/medqueue_*.sql.gz 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm -f
    KEPT=$(ls "$BACKUP_DIR"/medqueue_*.sql.gz 2>/dev/null | wc -l)

    send_telegram "✅ <b>MedQueue: Бэкап БД выполнен</b>

📦 Файл: <code>medqueue_$TIMESTAMP.sql.gz</code>
💾 Размер: <b>$SIZE</b>
🗂 Всего бэкапов: <b>$KEPT из $MAX_BACKUPS</b>
🕐 Время: <code>$(date)</code>"

    echo "[$(date)] Done. Kept $KEPT backups."
else
    echo "[$(date)] BACKUP FAILED!"
    send_telegram "🔥 <b>MedQueue: ОШИБКА бэкапа БД!</b>

❌ Не удалось создать резервную копию базы данных.
🕐 Время: <code>$(date)</code>

Немедленно проверьте сервер!"
    exit 1
fi
