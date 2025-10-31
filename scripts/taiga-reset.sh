#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"
ENV_FILE="$ROOT_DIR/docker/.env"

ADMIN_USER="${ADMIN_USER:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-}"
ADMIN_PASS="${ADMIN_PASS:-}"
CLEAN_ARGS=()

# Parse CLI flags
while [[ $# -gt 0 ]]; do
	case "$1" in
		--admin-pass)
			ADMIN_PASS="${2:-}"; shift 2;;
		--admin-user)
			ADMIN_USER="${2:-}"; shift 2;;
		--admin-email)
			ADMIN_EMAIL="${2:-}"; shift 2;;
		--purge-local)
			CLEAN_ARGS+=("--purge-local"); shift;;
		*)
			# ignore unknown for now
			shift;;
	esac
done

if [[ -z "$ADMIN_USER" ]]; then
	ADMIN_USER=$(git config --global user.name || true)
fi
if [[ -z "$ADMIN_USER" ]]; then
	ADMIN_USER=$(id -un 2>/dev/null || whoami 2>/dev/null || echo admin)
fi

if [[ -z "$ADMIN_EMAIL" ]]; then
	ADMIN_EMAIL=$(git config --global user.email || true)
fi
if [[ -z "$ADMIN_EMAIL" ]]; then
	host=$(hostname -f 2>/dev/null || hostname)
	ADMIN_EMAIL="${ADMIN_USER}@${host}"
fi

if [[ -z "$ADMIN_PASS" ]]; then
	echo "ADMIN_PASS is required (pass --admin-pass or export ADMIN_PASS)." >&2
	exit 2
fi

"$SCRIPT_DIR/taiga-clean.sh" --force ${CLEAN_ARGS[*]:-}

if [[ ! -f "$ENV_FILE" ]]; then
	echo "Missing $ENV_FILE. Copy docker/env.example to docker/.env and configure." >&2
	exit 1
fi

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

"$SCRIPT_DIR/taiga-wait.sh" --timeout 240

# Echo URLs for convenience
# shellcheck disable=SC2046
set -a; . "$ENV_FILE"; set +a
SCHEME="${TAIGA_SITES_SCHEME:-http}"
HOST="${TAIGA_SITES_DOMAIN:-localhost}"
PORT="${TAIGA_HTTP_PORT:-9000}"
echo "Taiga UI:   ${SCHEME}://${HOST}:${PORT}"
echo "Taiga API:  ${SCHEME}://${HOST}:${PORT}/api/v1/"

set +e
docker compose -f "$COMPOSE_FILE" exec -T \
	taiga-back sh -lc \
	"ADMIN_USER='$ADMIN_USER' ADMIN_EMAIL='$ADMIN_EMAIL' ADMIN_PASS='$ADMIN_PASS' /opt/venv/bin/python manage.py shell -c \"from django.contrib.auth import get_user_model; U=get_user_model(); import os; u=os.environ['ADMIN_USER']; e=os.environ['ADMIN_EMAIL']; p=os.environ['ADMIN_PASS']; print('creating admin', u, e); U.objects.filter(username=u).exists() or U.objects.create_superuser(u,e,p)\""
RC=$?
set -e
if [[ $RC -ne 0 ]]; then
	echo "Failed to create admin user" >&2
	exit $RC
fi

echo "Admin ready: $ADMIN_USER <$ADMIN_EMAIL>"
