#!/usr/bin/env bash

# Simple auth smoke test for Taiga
# - Fetches a token from taiga-back (inside container)
# - Verifies /users/me in-container via Python requests
# - Tests /users/me against gateway (http://localhost:9000)
# Usage:
#   scripts/tests/auth_smoke.sh [username] [password]
# Defaults:
#   username=admin, password=TestAdmin123
# Notes:
#   - Backend port 9001 exposure is temporary; we skip direct curl due to header quirks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.yml"

# Arg handling: if one arg is provided, treat it as password (username defaults to admin)
if [[ $# -eq 1 ]]; then
	USER_NAME="admin"
	USER_PASS="$1"
else
	USER_NAME="${1:-admin}"
	USER_PASS="${2:-TestAdmin123}"
fi

GATEWAY_URL="http://localhost:9000"

info() { printf "\033[1;34m[INFO]\033[0m %s\n" "$*" >&2; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*" >&2; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*" >&2; }

fetch_token() {
	local token=""; local i
	for i in 1 2 3; do
		info "Fetching token attempt $i for user='$USER_NAME'..."
		set +e
		token=$(docker compose -f "$COMPOSE_FILE" exec -T \
			-e U="$USER_NAME" -e P="$USER_PASS" taiga-back sh -lc \
			'/opt/venv/bin/python -c "import requests, json, os; u=os.environ.get(\"U\"); p=os.environ.get(\"P\"); r=requests.post(\"http://127.0.0.1:8000/api/v1/auth\", headers={\"Content-Type\":\"application/json\"}, data=json.dumps({\"type\":\"normal\",\"username\":u,\"password\":p})); print((r.json() or {}).get(\"auth_token\",\"\"))"')
		local rc=$?
		set -e
		token="$(echo -n "$token" | tr -d '\r\n')"
		if [[ $rc -eq 0 && -n "$token" ]]; then
			printf "%s" "$token"
			return 0
		fi
		sleep 1
	done
	return 1
}

http_code() {
	# args: URL [header...]
	local url="$1"; shift
	curl -s -o /dev/null -w "%{http_code}" "$url" "$@"
}

print_head() {
	# args: URL [header...]
	local url="$1"; shift
	curl -s -i "$url" "$@" | sed -n '1,20p'
}

print_body_snippet() {
	# args: URL [header...]
	local url="$1"; shift
	curl -s "$url" "$@" | head -c 256; echo
}

verify_in_container_me() {
	info "Verifying /users/me in-container with Python requests"
	set +e
	local out
	out=$(docker compose -f "$COMPOSE_FILE" exec -T \
		-e TKN="$1" taiga-back sh -lc \
		'/opt/venv/bin/python -c "import requests, os; t=os.environ.get(\"TKN\"); h={\"Authorization\":f\"Bearer {t}\"}; r=requests.get(\"http://127.0.0.1:8000/api/v1/users/me\", headers=h); print(r.status_code); print((r.headers or {})); print((r.text or \"\")[:256])"')
	local rc=$?
	set -e
	printf "%s\n" "$out"
	return $rc
}

main() {
	local TOKEN
	if ! TOKEN=$(fetch_token); then
		err "Cannot continue without token. Check credentials or backend."; exit 1
	fi
	info "Got token (len=${#TOKEN})"

	verify_in_container_me "$TOKEN" || warn "In-container /users/me check failed"

	info "Testing gateway ${GATEWAY_URL}/api/v1/users/me"
	local code_g
	code_g=$(http_code "${GATEWAY_URL}/api/v1/users/me" -H "Authorization: Bearer ${TOKEN}")
	printf "gateway HTTP %s\n" "$code_g"
	print_head "${GATEWAY_URL}/api/v1/users/me" -H "Authorization: Bearer ${TOKEN}" || true
	print_body_snippet "${GATEWAY_URL}/api/v1/users/me" -H "Authorization: Bearer ${TOKEN}" || true

	if [[ "$code_g" != "200" ]]; then
		warn "Gateway call did not return 200; check nginx headers/host forwarding."
	fi
}

main "$@"
