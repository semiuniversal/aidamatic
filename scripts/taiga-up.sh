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
	echo "Missing $ENV_FILE. Copy docker/.env.example to docker/.env and edit." >&2
	exit 1
fi

exec docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
