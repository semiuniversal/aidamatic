#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"
ENV_FILE="$ROOT_DIR/docker/.env"

if [ ! -f "$COMPOSE_FILE" ]; then
	echo "Missing $COMPOSE_FILE" >&2
	exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
	echo "Missing $ENV_FILE. Copy docker/env.example to docker/.env and edit." >&2
	exit 1
fi

# Start services
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

# Load env to print URLs
# shellcheck disable=SC2046
set -a; . "$ENV_FILE"; set +a
SCHEME="${TAIGA_SITES_SCHEME:-http}"
HOST="${TAIGA_SITES_DOMAIN:-localhost}"
FRONT_URL="${TAIGA_FRONTEND_URL:-${SCHEME}://${HOST}}"
RAW_API_URL="${TAIGA_BACKEND_URL:-${SCHEME}://${HOST}}"
API_URL="${RAW_API_URL%/}/api/v1/"

echo "Taiga UI:   ${FRONT_URL}"
echo "Taiga API:  ${API_URL}"
