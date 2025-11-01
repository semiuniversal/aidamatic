#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env"
ENV_LOCAL_FILE="$ROOT_DIR/docker/.env.local"
TOKEN_FILE="$ROOT_DIR/.taiga_token"
AUTH_DIR="$ROOT_DIR/.aida"
AUTH_FILE="$AUTH_DIR/auth.json"
IDENT_FILE="$AUTH_DIR/identities.json"

usage() {
	cat <<USAGE
Usage: 
  $(basename "$0") [--refresh] [--switch-user] [--whoami] [--profile NAME] [--activate]

Prompts for credentials if not supplied and binds identity in .aida/auth*.json.
Profiles store to .aida/auth.<profile>.json and .taiga_token.<profile>.
USAGE
}

REFRESH=0
SWITCH=0
WHOAMI=0
PROFILE=""
ACTIVATE=0
while [[ $# -gt 0 ]]; do
	case "$1" in
		--help) usage; exit 0;;
		--refresh) REFRESH=1; shift;;
		--switch-user) SWITCH=1; shift;;
		--whoami) WHOAMI=1; shift;;
		--profile) PROFILE="${2:-}"; shift 2;;
		--activate) ACTIVATE=1; shift;;
		*) shift;;
	esac
done

if [[ -n "$PROFILE" ]]; then
	TOKEN_FILE="$ROOT_DIR/.taiga_token.$PROFILE"
fi

if [[ $WHOAMI -eq 1 ]]; then
	if [[ -n "$PROFILE" ]]; then
		FILE="$AUTH_DIR/auth.$PROFILE.json"
	else
		FILE="$AUTH_FILE"
	fi
	if [[ -f "$FILE" ]]; then
		cat "$FILE"; exit 0
	else
		echo "No bound identity ($FILE missing)" >&2; exit 1
	fi
fi

PRE_BASE_URL="${TAIGA_BASE_URL:-}"
PRE_USER="${TAIGA_ADMIN_USER:-}"
PRE_PASS="${TAIGA_ADMIN_PASSWORD:-}"

if [[ -f "$ENV_FILE" ]]; then set -a; . "$ENV_FILE"; set +a; fi
if [[ -f "$ENV_LOCAL_FILE" ]]; then set -a; . "$ENV_LOCAL_FILE"; set +a; fi

if [[ -n "$PRE_BASE_URL" ]]; then TAIGA_BASE_URL="$PRE_BASE_URL"; fi
if [[ -n "$PRE_USER" ]]; then TAIGA_ADMIN_USER="$PRE_USER"; fi
if [[ -n "$PRE_PASS" ]]; then TAIGA_ADMIN_PASSWORD="$PRE_PASS"; fi

: "${TAIGA_BASE_URL:=http://localhost:9000}"
TAIGA_ADMIN_USER="${TAIGA_ADMIN_USER:-}"
TAIGA_ADMIN_PASSWORD="${TAIGA_ADMIN_PASSWORD:-}"

# If profile maps to identities.json, prefill
if [[ -f "$IDENT_FILE" && -n "$PROFILE" ]]; then
	case "$PROFILE" in
		developer)
			VALS="$($PYTHON_BIN -c 'import sys,json; d=json.load(open(sys.argv[1])); print((d.get("developer") or {}).get("username","")); print((d.get("developer") or {}).get("password",""))' "$IDENT_FILE" 2>/dev/null || true)"
			TAIGA_ADMIN_USER="${TAIGA_ADMIN_USER:-$(printf '%s' "$VALS" | sed -n '1p')}"
			TAIGA_ADMIN_PASSWORD="${TAIGA_ADMIN_PASSWORD:-$(printf '%s' "$VALS" | sed -n '2p')}"
			;;
		scrum)
			VALS="$($PYTHON_BIN -c 'import sys,json; d=json.load(open(sys.argv[1])); print((d.get("scrum") or {}).get("username","")); print((d.get("scrum") or {}).get("password",""))' "$IDENT_FILE" 2>/dev/null || true)"
			TAIGA_ADMIN_USER="${TAIGA_ADMIN_USER:-$(printf '%s' "$VALS" | sed -n '1p')}"
			TAIGA_ADMIN_PASSWORD="${TAIGA_ADMIN_PASSWORD:-$(printf '%s' "$VALS" | sed -n '2p')}"
			;;
	esac
fi

if [[ -z "${TAIGA_ADMIN_USER}" ]]; then
	read -r -p "Taiga username [admin]: " INPUT_USER || true
	TAIGA_ADMIN_USER="${INPUT_USER:-admin}"
fi
if [[ -z "${TAIGA_ADMIN_PASSWORD}" ]]; then
	read -rs -p "Taiga password for ${TAIGA_ADMIN_USER}: " INPUT_PASS || true; echo
	TAIGA_ADMIN_PASSWORD="${INPUT_PASS:-}"
fi

if [[ $REFRESH -eq 1 && -f "$TOKEN_FILE" ]]; then rm -f "$TOKEN_FILE" || true; fi
if [[ $REFRESH -eq 0 && -s "$TOKEN_FILE" ]]; then
	if [[ -n "$PROFILE" ]]; then
		cat "$TOKEN_FILE"; exit 0
	elif [[ -f "$AUTH_FILE" ]]; then
		cat "$TOKEN_FILE"; exit 0
	fi
fi

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

# Switching guard only applies to default auth.json
if [[ -z "$PROFILE" && -f "$AUTH_FILE" && $SWITCH -ne 1 ]]; then
	OLD_ID=$(sed -n 's/.*"user_id"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$AUTH_FILE" | head -n1 || true)
	if [[ -n "$OLD_ID" && "$OLD_ID" != "$USER_ID" ]]; then
		echo "Refusing to switch identity (bound user_id=$OLD_ID, new user_id=$USER_ID). Pass --switch-user to override." >&2
		exit 5
	fi
fi

# Persist token and auth files
if [[ -n "$PROFILE" ]]; then
	PROFILE_AUTH="$AUTH_DIR/auth.$PROFILE.json"
	echo -n "$TOKEN" > "$ROOT_DIR/.taiga_token.$PROFILE"; chmod 600 "$ROOT_DIR/.taiga_token.$PROFILE" || true
	TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
	cat > "$PROFILE_AUTH" <<JSON
{
  "base_url": "$TAIGA_BASE_URL",
  "user_id": $USER_ID,
  "username": "$USER_NAME",
  "email": "$USER_EMAIL",
  "token": "$TOKEN",
  "created_at": "$TS"
}
JSON
	chmod 600 "$PROFILE_AUTH" || true
	# Update identities.json (store only username/email; preserve existing password if any)
	if [[ -n "$PYTHON_BIN" ]]; then
		$PYTHON_BIN - "$IDENT_FILE" "$PROFILE" "$USER_NAME" "$USER_EMAIL" <<'PY'
import sys, json, os
path, profile, uname, email = sys.argv[1:5]
data = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        data = {}
node = data.get(profile) or {}
if uname:
    node["username"] = uname
if email:
    node["email"] = email
# preserve any existing password
if profile not in data or not isinstance(data.get(profile), dict):
    data[profile] = {}
data[profile].update(node)
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
PY
	fi
	if [[ $ACTIVATE -eq 1 ]]; then
		cp "$PROFILE_AUTH" "$AUTH_FILE"
	fi
	printf "%s" "$TOKEN"
	exit 0
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

