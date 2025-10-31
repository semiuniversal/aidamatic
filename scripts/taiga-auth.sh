#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env"
TOKEN_FILE="$ROOT_DIR/.taiga_token"

usage() {
	cat <<USAGE
Usage: 
  $(basename "$0") [--refresh]

Reads TAIGA_BASE_URL, TAIGA_ADMIN_USER, TAIGA_ADMIN_PASSWORD from docker/.env,
requests an auth token from Taiga, caches it to .taiga_token, and prints it.
USAGE
}

REFRESH=0
if [[ "${1:-}" == "--help" ]]; then
	usage; exit 0
elif [[ "${1:-}" == "--refresh" ]]; then
	REFRESH=1
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

if [[ $REFRESH -eq 0 && -s "$TOKEN_FILE" ]]; then
	cat "$TOKEN_FILE"
	exit 0
fi

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
	# Very simple fallback JSON extraction (best-effort, no jq required)
	TOKEN="$(printf '%s' "$RESP" | sed -n 's/.*"auth_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
fi

if [[ -z "$TOKEN" ]]; then
	echo "Failed to obtain token. Response was:" >&2
	echo "$RESP" >&2
	exit 3
fi

echo -n "$TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE" || true

echo "$TOKEN"

