#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env"
TOKEN_FILE="$ROOT_DIR/.taiga_token"
AUTH_SCRIPT="$SCRIPT_DIR/taiga-auth.sh"

usage() {
	cat <<USAGE
Usage: $(basename "$0") [--refresh] METHOD PATH [curl-args...]

Examples:
  $(basename "$0") GET /api/v1/projects
  $(basename "$0") POST /api/v1/projects -H 'Content-Type: application/json' -d '{"name":"Demo"}'
USAGE
}

REFRESH=0
if [[ "${1:-}" == "--help" || $# -lt 2 ]]; then
	usage; [[ "${1:-}" == "--help" ]] && exit 0 || exit 2
elif [[ "${1:-}" == "--refresh" ]]; then
	REFRESH=1; shift
fi

METHOD="$1"; shift
PATH_PART="$1"; shift

if [[ ! -f "$ENV_FILE" ]]; then
	echo "Missing $ENV_FILE. Copy docker/env.example to docker/.env." >&2
	exit 1
fi

# shellcheck disable=SC2046
set -a; . "$ENV_FILE"; set +a
: "${TAIGA_BASE_URL:=http://localhost:9000}"

if [[ $REFRESH -eq 1 || ! -s "$TOKEN_FILE" ]]; then
	TOKEN="$($AUTH_SCRIPT ${REFRESH:+--refresh})"
else
	TOKEN="$(cat "$TOKEN_FILE")"
fi

curl -sS -X "$METHOD" "$TAIGA_BASE_URL$PATH_PART" \
	-H "Authorization: Bearer $TOKEN" \
	"$@"

