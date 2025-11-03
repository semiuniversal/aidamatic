#!/usr/bin/env bash
set -euo pipefail

# Wait for Taiga gateway to respond HTTP 200 on / (HTML) and API root to be reachable
# Usage: scripts/taiga-wait.sh [--timeout SECONDS]

TIMEOUT=180
if [[ "${1:-}" == "--timeout" && -n "${2:-}" ]]; then
	TIMEOUT="$2"; shift 2
fi

start=$(date +%s)

fmt_elapsed() {
	local secs=$1
	printf "%02dm%02ds" $((secs/60)) $((secs%60))
}

print_wait() {
	local stage="$1"
	local now=$(date +%s)
	local elapsed=$(( now - start ))
	printf "Waiting for %s... (elapsed %s)\n" "$stage" "$(fmt_elapsed "$elapsed")" >&2
}

until curl -fsS http://localhost:9000/ >/dev/null 2>&1; do
	now=$(date +%s)
	if (( now - start > TIMEOUT )); then
		echo "Timeout waiting for Taiga gateway" >&2
		exit 1
	fi
	sleep 2
	print_wait "gateway"
done
	now=$(date +%s)
	echo "Gateway up (elapsed $(fmt_elapsed $((now - start))))"

until curl -fsS http://localhost:9000/api/v1/ >/dev/null 2>&1; do
	now=$(date +%s)
	if (( now - start > TIMEOUT )); then
		echo "Timeout waiting for Taiga API" >&2
		exit 1
	fi
	sleep 2
	print_wait "API"
done
	now=$(date +%s)
	echo "API up (elapsed $(fmt_elapsed $((now - start))))"

# Ensure auth endpoint responds (proves Django fully loaded)
until [ "$(curl -fsS -o /dev/null -w "%{http_code}" -H 'Content-Type: application/json' -d '{"type":"normal","username":"_","password":"_"}' http://localhost:9000/api/v1/auth || true)" = "401" ]; do
	now=$(date +%s)
	if (( now - start > TIMEOUT )); then
		echo "Timeout waiting for Taiga auth endpoint" >&2
		exit 1
	fi
	sleep 2
	print_wait "auth"

done
	now=$(date +%s)
	echo "Auth endpoint up (elapsed $(fmt_elapsed $((now - start))))"

# Grace period to allow backend to finish applying migrations
GRACE=15
echo "Applying backend grace period (${GRACE}s)..."
sleep "$GRACE"
now=$(date +%s)

echo "Taiga backend ready (total $(fmt_elapsed $((now - start))))"
