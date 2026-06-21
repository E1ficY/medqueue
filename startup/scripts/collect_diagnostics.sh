#!/usr/bin/env bash
set -euo pipefail

# Simple diagnostics for MedQueue docker stack.
# Usage: ./collect_diagnostics.sh [--restart]
# Run on the server that hosts the project (project root is assumed).

RESTART=0
if [ "${1:-}" = "--restart" ]; then
  RESTART=1
fi

TS=$(date +%Y%m%d_%H%M%S)
OUTDIR="/tmp/medqueue_diagnostics_${TS}"
mkdir -p "$OUTDIR"

COMPOSE_FILE="startup/docker-compose.yml"

echo "Collecting diagnostics into $OUTDIR"

echo "== docker compose ps ==" > "$OUTDIR/00_docker_ps.txt" 2>&1
docker compose -f "$COMPOSE_FILE" ps >> "$OUTDIR/00_docker_ps.txt" 2>&1 || true

echo "== docker compose config ==" > "$OUTDIR/01_docker_config.txt" 2>&1
docker compose -f "$COMPOSE_FILE" config >> "$OUTDIR/01_docker_config.txt" 2>&1 || true

echo "== docker compose images ==" > "$OUTDIR/02_docker_images.txt" 2>&1
docker compose -f "$COMPOSE_FILE" images >> "$OUTDIR/02_docker_images.txt" 2>&1 || true

echo "== nginx logs (last 500 lines) ==" > "$OUTDIR/10_nginx_logs.txt" 2>&1
docker compose -f "$COMPOSE_FILE" logs --no-color --tail=500 nginx >> "$OUTDIR/10_nginx_logs.txt" 2>&1 || true

echo "== backend logs (last 500 lines) ==" > "$OUTDIR/11_backend_logs.txt" 2>&1
docker compose -f "$COMPOSE_FILE" logs --no-color --tail=500 backend >> "$OUTDIR/11_backend_logs.txt" 2>&1 || true

echo "== last 200 lines system journal (if available) ==" > "$OUTDIR/12_journalctl.txt" 2>&1 || true
if command -v journalctl >/dev/null 2>&1; then
  journalctl -n 200 --no-pager >> "$OUTDIR/12_journalctl.txt" 2>&1 || true
else
  echo "journalctl not available on this host" >> "$OUTDIR/12_journalctl.txt"
fi

echo "== Check nginx cert files inside container ==" > "$OUTDIR/20_nginx_certs.txt" 2>&1
if docker compose -f "$COMPOSE_FILE" ps --services | grep -q '^nginx$'; then
  docker compose -f "$COMPOSE_FILE" exec -T nginx ls -la /etc/letsencrypt/live/medqueue.me >> "$OUTDIR/20_nginx_certs.txt" 2>&1 || echo "Could not list certs or path missing" >> "$OUTDIR/20_nginx_certs.txt"
else
  echo "nginx service not present in compose" >> "$OUTDIR/20_nginx_certs.txt"
fi

echo "== Local HTTP/HTTPS checks ==" > "$OUTDIR/30_local_http.txt" 2>&1
curl -I --max-time 5 http://127.0.0.1 >> "$OUTDIR/30_local_http.txt" 2>&1 || echo "http check failed" >> "$OUTDIR/30_local_http.txt"
curl -vk --max-time 10 https://127.0.0.1 >> "$OUTDIR/30_local_http.txt" 2>&1 || echo "https local check failed" >> "$OUTDIR/30_local_http.txt"

echo "== Public domain checks ==" > "$OUTDIR/31_public_checks.txt" 2>&1
if command -v dig >/dev/null 2>&1; then
  dig +short medqueue.me >> "$OUTDIR/31_public_checks.txt" 2>&1 || true
else
  echo "dig not available" >> "$OUTDIR/31_public_checks.txt"
fi
curl -Ik --max-time 10 https://medqueue.me >> "$OUTDIR/31_public_checks.txt" 2>&1 || echo "public curl failed" >> "$OUTDIR/31_public_checks.txt"

echo "== Attempt to query backend from within backend container ==" > "$OUTDIR/40_backend_selfcheck.txt" 2>&1
if docker compose -f "$COMPOSE_FILE" ps --services | grep -q '^backend$'; then
  docker compose -f "$COMPOSE_FILE" exec -T backend sh -c 'curl -I --max-time 5 http://127.0.0.1:8000 || curl -I --max-time 5 http://backend:8000' >> "$OUTDIR/40_backend_selfcheck.txt" 2>&1 || echo "backend internal curl failed" >> "$OUTDIR/40_backend_selfcheck.txt"
else
  echo "backend service not present in compose" >> "$OUTDIR/40_backend_selfcheck.txt"
fi

echo "Diagnostics collected. Files in: $OUTDIR"

if [ "$RESTART" -eq 1 ]; then
  echo "\n-- Restarting backend and nginx services --"
  docker compose -f "$COMPOSE_FILE" up -d --build backend nginx || echo "Restart failed"
  echo "Waiting 6 seconds for services to settle..."
  sleep 6
  echo "Collecting short follow-up logs..."
  docker compose -f "$COMPOSE_FILE" logs --no-color --tail=200 nginx >> "$OUTDIR/50_nginx_followup.txt" 2>&1 || true
  docker compose -f "$COMPOSE_FILE" logs --no-color --tail=200 backend >> "$OUTDIR/51_backend_followup.txt" 2>&1 || true
  echo "Restart done. Follow-up logs saved to $OUTDIR"
fi

echo "\nArchive created at: $OUTDIR"
echo "You can tar.gz it: tar -czf /tmp/medqueue_diagnostics_${TS}.tar.gz -C /tmp medqueue_diagnostics_${TS}"

exit 0
