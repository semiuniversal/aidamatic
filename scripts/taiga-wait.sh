#!/usr/bin/env bash
set -euo pipefail

# Wait for Taiga gateway to respond HTTP 200 on / (HTML) and API root to be reachable
# Usage: scripts/taiga-wait.sh [--timeout SECONDS]

TIMEOUT=180
if [[ "${1:-}" == "--timeout" && -n "${2:-}" ]]; then
	TIMEOUT="$2"; shift 2
fi

start=$(date +%s)

until curl -fsS http://localhost:9000/ >/dev/null 2>&1; do
	now=$(date +%s)
	if (( now - start > TIMEOUT )); then
		echo "Timeout waiting for Taiga gateway" >&2
		exit 1
	fi
	sleep 2
	echo "Waiting for gateway..." >&2
done

echo "Gateway up"

until curl -fsS http://localhost:9000/api/v1/ >/dev/null 2>&1; do
	now=$(date +%s)
	if (( now - start > TIMEOUT )); then
		echo "Timeout waiting for Taiga API" >&2
		exit 1
	fi
	sleep 2
	echo "Waiting for API..." >&2
done

echo "API up"
