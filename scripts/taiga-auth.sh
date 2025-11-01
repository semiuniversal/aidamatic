#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env"
ENV_LOCAL_FILE="$ROOT_DIR/docker/.env.local"
TOKEN_FILE="$ROOT_DIR/.taiga_token"
AUTH_DIR="$ROOT_DIR/.aida"
AUTH_FILE="$AUTH_DIR/auth.json"

usage() {
	cat <<USAGE
Usage: 
  $(basename "$0") [--refresh] [--switch-user] [--whoami]

Prompts for credentials if not supplied and binds identity in .aida/auth.json.
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
		cat "$AUTH_FILE"; exit 0
	else
		echo "No bound identity (.aida/auth.json missing)" >&2; exit 1
	fi
fi

# Preserve preexisting env
PRE_BASE_URL="${TAIGA_BASE_URL:-}"
PRE_USER="${TAIGA_ADMIN_USER:-}"
PRE_PASS="${TAIGA_ADMIN_PASSWORD:-}"

# Source optional env files
if [[ -f "$ENV_FILE" ]]; then set -a; . "$ENV_FILE"; set +a; fi
if [[ -f "$ENV_LOCAL_FILE" ]]; then set -a; . "$ENV_LOCAL_FILE"; set +a; fi

# Re-apply shell-provided values
if [[ -n "$PRE_BASE_URL" ]]; then TAIGA_BASE_URL="$PRE_BASE_URL"; fi
if [[ -n "$PRE_USER" ]]; then TAIGA_ADMIN_USER="$PRE_USER"; fi
if [[ -n "$PRE_PASS" ]]; then TAIGA_ADMIN_PASSWORD="$PRE_PASS"; fi

: "${TAIGA_BASE_URL:=http://localhost:9000}"
TAIGA_ADMIN_USER="${TAIGA_ADMIN_USER:-}"
TAIGA_ADMIN_PASSWORD="${TAIGA_ADMIN_PASSWORD:-}"

# Interactive prompts if missing
if [[ -z "${TAIGA_ADMIN_USER}" ]]; then
	read -r -p "Taiga username [admin]: " INPUT_USER || true
	TAIGA_ADMIN_USER="${INPUT_USER:-admin}"
fi
if [[ -z "${TAIGA_ADMIN_PASSWORD}" ]]; then
	read -rs -p "Taiga password for ${TAIGA_ADMIN_USER}: " INPUT_PASS || true; echo
	TAIGA_ADMIN_PASSWORD="${INPUT_PASS:-}"
fi

# Refresh handling
if [[ $REFRESH -eq 1 && -f "$TOKEN_FILE" ]]; then rm -f "$TOKEN_FILE" || true; fi
if [[ $REFRESH -eq 0 && -s "$TOKEN_FILE" && -f "$AUTH_FILE" ]]; then
	cat "$TOKEN_FILE"; exit 0
fi

# Authenticate
RESP=$(curl -sS "$TAIGA_BASE_URL/api/v1/auth" -H 'Content-Type: application/json' -d "{\"type\":\"normal\",\"username\":\"$TAIGA_ADMIN_USER\",\"password\":\"$TAIGA_ADMIN_PASSWORD\"}")

PYTHON_BIN="$(command -v python3 || true)"; [[ -z "$PYTHON_BIN" ]] && PYTHON_BIN="$(command -v python || true)"
TOKEN=""
if [[ -n "$PYTHON_BIN" ]]; then
	TOKEN="$($PYTHON_BIN -c 'import sys,json; 
try:
	data=json.loads(sys.stdin.read()); print(data.get("auth_token",""))
except Exception: print("")' <<< "$RESP")"
fi
[[ -z "$TOKEN" ]] && TOKEN="$(printf '%s' "$RESP" | sed -n 's/.*"auth_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
[[ -z "$TOKEN" ]] && { echo "Failed to obtain token. Response was:" >&2; echo "$RESP" >&2; exit 3; }

# Resolve identity
ME=$(curl -sS "$TAIGA_BASE_URL/api/v1/users/me" -H "Authorization: Bearer $TOKEN") || true
USER_ID=""; USER_NAME=""; USER_EMAIL=""
if [[ -n "$PYTHON_BIN" ]]; then
	readarray -t FIELDS < <($PYTHON_BIN -c 'import sys,json; 
try:
	d=json.loads(sys.stdin.read()); print(d.get("id","")); print(d.get("username","")); print(d.get("email",""))
except Exception: print(""); print(""); print("")' <<< "$ME")
	USER_ID="${FIELDS[0]}"; USER_NAME="${FIELDS[1]}"; USER_EMAIL="${FIELDS[2]}"
fi
[[ -z "$USER_ID" ]] && { echo "Failed to resolve identity from /users/me" >&2; exit 4; }

mkdir -p "$AUTH_DIR"
if [[ -f "$AUTH_FILE" && $SWITCH -ne 1 ]]; then
	OLD_ID=$(sed -n 's/.*"user_id"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$AUTH_FILE" | head -n1 || true)
	if [[ -n "$OLD_ID" && "$OLD_ID" != "$USER_ID" ]]; then
		echo "Refusing to switch identity (bound user_id=$OLD_ID, new user_id=$USER_ID). Pass --switch-user to override." >&2
		exit 5
	fi
fi

echo -n "$TOKEN" > "$TOKEN_FILE"; chmod 600 "$TOKEN_FILE" || true
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

echo "$TOKEN"

