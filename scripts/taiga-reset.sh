#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"
ENV_FILE="$ROOT_DIR/docker/.env"
AUTH_DIR="$ROOT_DIR/.aida"
IDENT_FILE="$AUTH_DIR/identities.json"

ADMIN_USER="${ADMIN_USER:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-}"
ADMIN_PASS="${ADMIN_PASS:-}"
CLEAN_ARGS=()

# Parse CLI flags
while [[ $# -gt 0 ]]; do
	case "$1" in
		--admin-pass) ADMIN_PASS="${2:-}"; shift 2;;
		--admin-user) ADMIN_USER="${2:-}"; shift 2;;
		--admin-email) ADMIN_EMAIL="${2:-}"; shift 2;;
		--purge-local) CLEAN_ARGS+=("--purge-local"); shift;;
		*) shift;;
	esac
done

if [[ -z "$ADMIN_USER" ]]; then ADMIN_USER=$(git config --global user.name || true); fi
if [[ -z "$ADMIN_USER" ]]; then ADMIN_USER=$(id -un 2>/dev/null || whoami 2>/dev/null || echo admin); fi
if [[ -z "$ADMIN_EMAIL" ]]; then ADMIN_EMAIL=$(git config --global user.email || true); fi
if [[ -z "$ADMIN_EMAIL" ]]; then host=$(hostname -f 2>/dev/null || hostname); ADMIN_EMAIL="${ADMIN_USER}@${host}"; fi

# Prompt for password if missing (no storage anywhere)
if [[ -z "$ADMIN_PASS" ]]; then
	read -rs -p "Set admin password for ${ADMIN_USER}: " INPUT_PASS || true; echo
	ADMIN_PASS="${INPUT_PASS:-}"
fi

"$SCRIPT_DIR/taiga-clean.sh" --force ${CLEAN_ARGS[*]:-}

if [[ ! -f "$ENV_FILE" ]]; then
	echo "Missing $ENV_FILE. Copy docker/env.example to docker/.env and configure." >&2
	exit 1
fi

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

"$SCRIPT_DIR/taiga-wait.sh" --timeout 240

# Extra grace period – defensive to avoid racing migrations
sleep 10

# Create admin user with retries (defensive)
create_admin() {
	for i in 1 2 3 4 5; do
		set +e
		docker compose -f "$COMPOSE_FILE" exec -T \
			taiga-back sh -lc \
			"ADMIN_USER='$ADMIN_USER' ADMIN_EMAIL='$ADMIN_EMAIL' ADMIN_PASS='$ADMIN_PASS' /opt/venv/bin/python manage.py shell -c \"from django.contrib.auth import get_user_model; U=get_user_model(); import os; u=os.environ['ADMIN_USER']; e=os.environ['ADMIN_EMAIL']; p=os.environ['ADMIN_PASS']; print('creating user (admin privileges)', u, e); U.objects.filter(username=u).exists() or U.objects.create_superuser(u,e,p)\""
		RC=$?
		set -e
		if [[ $RC -eq 0 ]]; then
			return 0
		fi
		echo "Admin create attempt $i failed; waiting before retry..." >&2
		sleep 5
	done
	return 1
}

if ! create_admin; then
	echo "Warning: failed to create admin user after retries. You can run createsuperuser inside the container later." >&2
fi

# Generate non-human users (ide, scrum) with random passwords
mkdir -p "$AUTH_DIR"
PYBIN="$(command -v python3 || true)"; [[ -z "$PYBIN" ]] && PYBIN="$(command -v python || true)"
GEN_DEV_PASS="$($PYBIN - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)"
GEN_SCRUM_PASS="$($PYBIN - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)"
DEV_USER="ide"
DEV_EMAIL="ide@local"
SCRUM_USER="scrum"
SCRUM_EMAIL="scrum@local"

# Create users in Taiga with retries (defensive)
create_agents() {
	for i in 1 2 3 4 5; do
		set +e
		docker compose -f "$COMPOSE_FILE" exec -T taiga-back sh -lc \
			"DEV_USER='$DEV_USER' DEV_EMAIL='$DEV_EMAIL' DEV_PASS='$GEN_DEV_PASS' SCRUM_USER='$SCRUM_USER' SCRUM_EMAIL='$SCRUM_EMAIL' SCRUM_PASS='$GEN_SCRUM_PASS' /opt/venv/bin/python manage.py shell -c \"from django.contrib.auth import get_user_model; import os; U=get_user_model(); 
for key in [('DEV_USER','DEV_EMAIL','DEV_PASS'), ('SCRUM_USER','SCRUM_EMAIL','SCRUM_PASS')]:
    u=os.environ[key[0]]; e=os.environ[key[1]]; p=os.environ[key[2]]
    print('creating user', u, e)
    obj, created = U.objects.get_or_create(username=u, defaults={'email': e})
    if created:
        obj.set_password(p); obj.is_active=True; obj.save()
    else:
        obj.email=e; obj.is_active=True; obj.set_password(p); obj.save()
\""
		RC=$?
		set -e
		if [[ $RC -eq 0 ]]; then
			return 0
		fi
		echo "Agent create attempt $i failed; waiting before retry..." >&2
		sleep 5
	done
	return 1
}

if ! create_agents; then
	echo "Warning: failed to create ide/scrum users after retries. You can create them later from the UI." >&2
fi

# Persist identities locally (store passwords only for non-human profiles)
cat > "$IDENT_FILE" <<JSON
{
  "user": { "username": "$ADMIN_USER", "email": "$ADMIN_EMAIL" },
  "ide": { "username": "$DEV_USER", "email": "$DEV_EMAIL", "password": "$GEN_DEV_PASS" },
  "scrum": { "username": "$SCRUM_USER", "email": "$SCRUM_EMAIL", "password": "$GEN_SCRUM_PASS" }
}
JSON
chmod 600 "$IDENT_FILE" || true

# Echo URLs (avoid duplicating port)
set -a; . "$ENV_FILE"; set +a
SCHEME="${TAIGA_SITES_SCHEME:-http}"; HOST="${TAIGA_SITES_DOMAIN:-localhost}"
FRONT_URL="${TAIGA_FRONTEND_URL:-${SCHEME}://${HOST}}"
RAW_API_URL="${TAIGA_BACKEND_URL:-${SCHEME}://${HOST}}"
API_URL="${RAW_API_URL%/}/api/v1/"
echo "Taiga UI:   ${FRONT_URL}"
echo "Taiga API:  ${API_URL}"

echo "User ready (admin privileges): $ADMIN_USER <$ADMIN_EMAIL>"
