#!/usr/bin/env bash
# Run on the VPS (manually or via GitHub Actions SSH).
# Usage: DEPLOY_REF=main ./deploy/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REF="${DEPLOY_REF:-main}"
COMPOSE=(docker compose -f docker-compose.prod.yml)

echo "==> Deploying SON at $ROOT (ref=$REF)"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.example and configure before deploying." >&2
  exit 1
fi

git fetch origin
git checkout "$REF"
git pull --ff-only origin "$REF"

"${COMPOSE[@]}" up -d --build --remove-orphans
"${COMPOSE[@]}" ps

# shellcheck disable=SC1091
set -a && source .env && set +a
DOMAIN="${SON_DOMAIN:-}"
if [[ -n "$DOMAIN" ]]; then
  echo "==> Health https://${DOMAIN}/health"
  curl -fsS --max-time 30 "https://${DOMAIN}/health" || true
  echo
else
  echo "==> Health via compose exec"
  "${COMPOSE[@]}" exec -T api curl -fsS --max-time 15 http://127.0.0.1:8000/health || true
  echo
fi

echo "==> Deploy finished"
