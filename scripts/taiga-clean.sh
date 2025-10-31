#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"

CONFIRM=0
if [[ "${1:-}" == "--yes" ]]; then
	CONFIRM=1
fi

if [[ "${AIDA_FORCE:-}" == "1" ]]; then
	CONFIRM=1
fi

if [[ $CONFIRM -ne 1 ]]; then
	echo "This will stop Taiga and remove all volumes (data loss). Re-run with --yes or set AIDA_FORCE=1." >&2
	exit 2
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
	echo "Missing $COMPOSE_FILE" >&2
	exit 1
fi

# Stop and remove volumes
exec docker compose -f "$COMPOSE_FILE" down -v
