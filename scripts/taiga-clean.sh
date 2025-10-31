#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"

FORCE=0
PURGE_LOCAL=0

for arg in "$@"; do
	case "$arg" in
		--force)
			FORCE=1;
			shift;;
		--yes) # backward-compat alias for --force
			FORCE=1;
			shift;;
		--purge-local)
			PURGE_LOCAL=1;
			shift;;
		*) ;;
	esac
done

if [[ $FORCE -ne 1 ]]; then
	echo "This will STOP Taiga and REMOVE Docker volumes (data loss)." >&2
	echo "Lost data includes: users, projects, items, comments, attachments/media, and all Taiga configuration stored in volumes (taiga-db, taiga-media, taiga-static)." >&2
	echo "If you also pass --purge-local, it will delete local AIDA state (.aida/) and .taiga_token." >&2
	echo "Re-run with --force to proceed." >&2
	exit 2
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
	echo "Missing $COMPOSE_FILE" >&2
	exit 1
fi

# Stop and remove volumes (taiga-db, taiga-media, taiga-static)
docker compose -f "$COMPOSE_FILE" down -v

echo "Docker volumes removed (taiga-db, taiga-media, taiga-static)."

if [[ $PURGE_LOCAL -eq 1 ]]; then
	# Purge local AIDA state
	rm -rf "$ROOT_DIR/.aida" "$ROOT_DIR/.taiga_token" || true
	echo "Purged local AIDA state (.aida/, .taiga_token)."
fi
