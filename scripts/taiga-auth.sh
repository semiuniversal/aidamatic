#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env"
TOKEN_FILE="$ROOT_DIR/.taiga_token"
AUTH_DIR="$ROOT_DIR/.aida"
AUTH_FILE="$AUTH_DIR/auth.json"

usage() {
	cat <<USAGE
Usage: 
  $(basename "$0") [--refresh] [--switch-user] [--whoami]

Reads TAIGA_BASE_URL, TAIGA_ADMIN_USER, TAIGA_ADMIN_PASSWORD from docker/.env,
requests an auth token from Taiga, caches it to .taiga_token and binds identity
in .aida/auth.json (base_url, user_id, username, email, token).

Options:
  --refresh       Force re-auth (removes cached token before fetching)
  --switch-user   Allow overwriting .aida/auth.json if identity differs
  --whoami        Print bound identity from .aida/auth.json and exit
USAGE
}

REFRESH=0
SWITCH=0
WHOAMI=0
while [[ $# -gt 0 ]]; do
	case "$1" in
		--help) usage; exit 0;;
		--refresh) REFRESH=1; shift;;
		--switch-user) SWITCH=1; shift;;
		--whoami) WHOAMI=1; shift;;
		*) shift;;
	esac
done

if [[ $WHOAMI -eq 1 ]]; then
	if [[ -f "$AUTH_FILE" ]]; then
		cat "$AUTH_FILE"
		exit 0
	else
		echo "No bound identity (.aida/auth.json missing)" >&2
		exit 1
	fi
fi

if [[ ! -f "$ENV_FILE" ]]; then
	echo "Missing $ENV_FILE. Copy docker/env.example to docker/.env and set admin creds." >&2
	exit 1
fi

# shellcheck disable=SC2046
set -a; . "$ENV_FILE"; set +a

: "${TAIGA_BASE_URL:=http://localhost:9000}"
: "${TAIGA_ADMIN_USER:=admin}"
: "${TAIGA_ADMIN_PASSWORD:=}"

if [[ -z "$TAIGA_ADMIN_PASSWORD" ]]; then
	echo "TAIGA_ADMIN_PASSWORD is not set in $ENV_FILE" >&2
	exit 2
fi

# If refresh requested, remove cached token first to avoid confusion
if [[ $REFRESH -eq 1 && -f "$TOKEN_FILE" ]]; then
	rm -f "$TOKEN_FILE" || true
fi

if [[ $REFRESH -eq 0 && -s "$TOKEN_FILE" ]]; then
	# Ensure token corresponds to the same identity; if auth file exists, just print token
	if [[ -f "$AUTH_FILE" ]]; then
		cat "$TOKEN_FILE"
		exit 0
	fi
fi

# Authenticate
RESP=$(curl -sS "$TAIGA_BASE_URL/api/v1/auth" \
	-H 'Content-Type: application/json' \
	-d "{\"type\":\"normal\",\"username\":\"$TAIGA_ADMIN_USER\",\"password\":\"$TAIGA_ADMIN_PASSWORD\"}")

# Prefer python3/python to parse JSON from stdin; fallback to sed if unavailable.
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
	PYTHON_BIN="$(command -v python || true)"
fi

TOKEN=""
if [[ -n "$PYTHON_BIN" ]]; then
	TOKEN="$($PYTHON_BIN -c 'import sys, json; 
try:
	data = json.loads(sys.stdin.read()); 
	print(data.get("auth_token", ""))
except Exception:
	print("")' <<< "$RESP")"
fi

if [[ -z "$TOKEN" ]]; then
	TOKEN="$(printf '%s' "$RESP" | sed -n 's/.*"auth_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
fi

if [[ -z "$TOKEN" ]]; then
	echo "Failed to obtain token. Response was:" >&2
	echo "$RESP" >&2
	exit 3
fi

# Resolve identity via /users/me
ME=$(curl -sS "$TAIGA_BASE_URL/api/v1/users/me" -H "Authorization: Bearer $TOKEN") || true
USER_ID=""
USER_NAME=""
USER_EMAIL=""
if [[ -n "$PYTHON_BIN" ]]; then
	readarray -t FIELDS < <($PYTHON_BIN -c 'import sys,json; 
try:
	d=json.loads(sys.stdin.read());
	print(d.get("id","")); print(d.get("username","")); print(d.get("email",""))
except Exception:
	print(""); print(""); print("")
') <<< "$ME")
	USER_ID="${FIELDS[0]}"
	USER_NAME="${FIELDS[1]}"
	USER_EMAIL="${FIELDS[2]}"
fi

if [[ -z "$USER_ID" ]]; then
	echo "Failed to resolve identity from /users/me" >&2
	exit 4
fi

mkdir -p "$AUTH_DIR"

# If existing auth bound to another user and no --switch-user, refuse
if [[ -f "$AUTH_FILE" && $SWITCH -ne 1 ]]; then
	OLD_ID=$(sed -n 's/.*"user_id"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$AUTH_FILE" | head -n1 || true)
	if [[ -n "$OLD_ID" && "$OLD_ID" != "$USER_ID" ]]; then
		echo "Refusing to switch identity (bound user_id=$OLD_ID, new user_id=$USER_ID). Pass --switch-user to override." >&2
		exit 5
	fi
fi

# Write token cache
echo -n "$TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE" || true

# Write auth.json (bind identity)
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
cat > "$AUTH_FILE" <<JSON
{
  "base_url": "$TAIGA_BASE_URL",
  "user_id": $USER_ID,
  "username": "$USER_NAME",
  "email": "$USER_EMAIL",
  "token": "$TOKEN",
  "created_at": "$TS"
}
JSON
chmod 600 "$AUTH_FILE" || true

# Print token (for callers expecting stdout)
echo "$TOKEN"

