#!/usr/bin/env bash
# Быстрый деплой auth.html + nginx + backend на сервере (из каталога startup).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif docker-compose version >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "docker compose not found" >&2
  exit 1
fi

if [[ ! -f backend/.env ]]; then
  echo "ERROR: backend/.env not found."
  echo "Create it from backend/.env.example and set TURNSTILE_SECRET_KEY, EMAIL_*"
  exit 1
fi

if ! grep -q '^TURNSTILE_SECRET_KEY=.\+' backend/.env 2>/dev/null; then
  echo "WARNING: TURNSTILE_SECRET_KEY is empty in backend/.env — регистрация не будет работать."
fi

echo "Rebuilding backend + nginx..."
$DC up -d --build backend nginx

echo "Waiting for backend migrations..."
sleep 5
$DC logs --tail 30 backend

echo "Check auth.html marker on this server:"
grep -m1 'auth build' html/auth.html || true

echo "Done. Open https://medqueue.me/auth.html and Ctrl+Shift+R"
echo "In page source you should see: MedQueue auth build: 2026-05-25-v5"
