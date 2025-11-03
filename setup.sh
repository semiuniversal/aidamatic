#!/bin/bash

set -euo pipefail

separator() {
    printf -- '------------------------------------------------------------\n'
}

echo "Starting project environment setup..."
separator

# Args: --init to run aida-setup --init, --start to run aida-start, --no-uv-install to skip uv bootstrap, --bootstrap for full one-line install
INIT=0
START=0
NO_UV_INSTALL=0
BOOTSTRAP=0
for arg in "$@"; do
    case "$arg" in
        --init) INIT=1 ;;
        --start) START=1 ;;
        --no-uv-install) NO_UV_INSTALL=1 ;;
        --bootstrap) BOOTSTRAP=1 ;;
    esac
done

# Step 1: Check if 'uv' command is available (unless skipped)
if ! command -v uv >/dev/null 2>&1; then
    if [ "$NO_UV_INSTALL" -eq 1 ]; then
        echo "'uv' command not found and --no-uv-install set; continuing (ensure uv exists if you expect it)."
    else
        echo "'uv' command not found. Installing 'uv' now..."

        # Detect OS and install uv accordingly
        # Here assuming curl and bash are available
        if command -v curl >/dev/null 2>&1; then
            bash -c "$(curl -fsSL https://astral.sh/uv/install.sh)" || {
                echo "Error: Failed to install 'uv'. Please install it manually following instructions at https://astral.sh/uv"
                exit 1
            }
        else
            echo "Error: curl is required to install 'uv' automatically."
            echo "Please install 'uv' manually following instructions at https://astral.sh/uv"
            exit 1
        fi

        # Try to update PATH in current session to include ~/.local/bin if it exists
        UV_PATH="$HOME/.local/bin"
        if [ -d "$UV_PATH" ] && [[ ":$PATH:" != *":$UV_PATH:"* ]]; then
            export PATH="$UV_PATH:$PATH"
            echo "Temporarily added '$UV_PATH' to PATH for this session."
        fi

        # Check if uv is now available
        if ! command -v uv >/dev/null 2>&1; then
            echo "'uv' was installed but is not found in the current shell."
            echo "Please close this terminal and open a new one, then rerun this script."
            exit 0
        else
            echo "'uv' installed successfully!"
        fi
    fi
else
    echo "'uv' command found."
fi

separator

# Step 2: Check Docker / Compose prerequisites (required for Taiga)
if ! command -v docker >/dev/null 2>&1; then
    echo "Error: Docker is required. Install Docker Desktop (enable WSL2 integration on Windows)." >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Error: Docker Compose (v2) is required. Upgrade Docker Desktop or install compose-plugin." >&2
    exit 1
fi

# Step 3: Ensure virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment '.venv' not found. Creating using 'uv venv'..."
    uv venv || {
        echo "Failed to create virtual environment. Please check 'uv' installation."
        exit 1
    }
    echo "Virtual environment created successfully."
else
    echo "Virtual environment '.venv' already exists."
fi

separator

# Step 4: Activate the virtual environment
# Prefer .venv/bin/activate (Unix style)
ACTIVATE_SCRIPT=".venv/bin/activate"

if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    echo "Error: Activation script '$ACTIVATE_SCRIPT' not found."
    echo "Make sure the virtual environment was created correctly."
    exit 1
fi

echo "Activating the virtual environment..."
# shellcheck source=/dev/null
source "$ACTIVATE_SCRIPT"
echo "Activate exit code: $?"
echo "Virtual environment activated."

separator

# Step 5: Verify Python interpreter and version
PYTHON_BIN=".venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "Error: Python interpreter not found at '$PYTHON_BIN'."
    echo "Try deleting '.venv' and rerunning the setup."
    exit 1
fi
PYV="$($PYTHON_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
PYMAJMIN="$(echo "$PYV" | cut -d. -f1-2)"
case "$PYMAJMIN" in
    3.10|3.11|3.12|3.13) : ;;
    *) echo "Error: Python $PYV found; need >= 3.10" >&2; exit 1 ;;
esac

aida_env_prepare() {
    # Create docker/.env from example if missing
    if [ ! -f "docker/.env" ] && [ -f "docker/env.example" ]; then
        cp docker/env.example docker/.env
        echo "Created docker/.env from example."
    fi
}

aida_env_prepare

separator

# Step 6: Install dependencies (editable mode)
echo "Installing dependencies in editable mode with 'uv pip install -e .'..."
uv pip install -e . || {
    echo "Dependency installation failed."
    exit 1
}
echo "Dependencies installed successfully."

separator

# Bootstrap flow
if [ "$BOOTSTRAP" -eq 1 ]; then
    echo "Running full bootstrap (destructive reset + init + start)..."
    echo "This can take several minutes (3-5). Progress messages will appear; please do not interrupt."
    BOOTSTRAP_STARTED=$(date +%s)
    ADMIN_USER="user"
    ADMIN_EMAIL="user@localhost"
    DEFAULT_ADMIN_PASS="$($PYTHON_BIN - <<'PY'
import secrets
print(secrets.token_urlsafe(16))
PY
)"
    if [ -z "$DEFAULT_ADMIN_PASS" ]; then
        DEFAULT_ADMIN_PASS="tmpPass!123"
    fi

    if [ -z "${AIDA_BOOTSTRAP_ADMIN_PASS:-}" ]; then
        printf "Admin password for Taiga user '%s' (leave blank to auto-generate): " "$ADMIN_USER"
        stty_state=$(stty -g 2>/dev/null || printf '')
        if stty -echo 2>/dev/null; then
            read -r ADMIN_PASS_INPUT
            stty "$stty_state" 2>/dev/null || true
            printf "\n"
        else
            read -r ADMIN_PASS_INPUT
        fi
        if [ -z "$ADMIN_PASS_INPUT" ]; then
            ADMIN_PASS="$DEFAULT_ADMIN_PASS"
            echo "Generated admin password automatically."
        else
            ADMIN_PASS="$ADMIN_PASS_INPUT"
        fi
    else
        ADMIN_PASS="$AIDA_BOOTSTRAP_ADMIN_PASS"
        echo "Using admin password provided via AIDA_BOOTSTRAP_ADMIN_PASS."
    fi
    if [ -z "$ADMIN_PASS" ]; then
        ADMIN_PASS="$DEFAULT_ADMIN_PASS"
        echo "Warning: Generated fallback admin password."
    fi

    if ! aida-setup --reset --force --yes --admin-user "$ADMIN_USER" --admin-email "$ADMIN_EMAIL" --admin-pass "$ADMIN_PASS"; then
        echo "Bootstrap reset failed. Aborting."
        exit 1
    fi

    echo "Starting AIDA (this may take several minutes)..."
    if ! aida-start; then
        echo "Bootstrap failed during aida-start. Check logs above." >&2
        exit 1
    fi

    BOOTSTRAP_ENDED=$(date +%s)
    ELAPSED=$((BOOTSTRAP_ENDED - BOOTSTRAP_STARTED))
    printf "\nBootstrap complete in %02dm%02ds.\n" $((ELAPSED/60)) $((ELAPSED%60))
    echo "Login to Taiga: http://localhost:9000"
    echo "  username: $ADMIN_USER"
    echo "  password: $ADMIN_PASS"
    echo "Agent credentials (if provisioned) will be in .aida/identities.json"
    exit 0
fi

# Optional: initialize and start services if requested
if [ "$INIT" -eq 1 ]; then
    echo "Running aida-setup --init ..."
    if command -v aida-setup >/dev/null 2>&1; then
        aida-setup --init || true
    else
        "$PYTHON_BIN" -m aidamatic.cli.aida_setup --init || true
    fi
fi
if [ "$START" -eq 1 ]; then
    echo "Running aida-start ..."
    if command -v aida-start >/dev/null 2>&1; then
        aida-start || true
    else
        "$PYTHON_BIN" -m aidamatic.cli.aidastart || true
    fi
fi

# Final message
echo "Setup complete! 🎉"
echo "Virtualenv activation from inside a script does not persist outside the script." \
     "Use a shell alias to chain setup and activation in your terminal session."
echo
echo "Suggested reusable alias (add to your shell rc):"
echo "  alias av=\"./setup.sh && source .venv/bin/activate && rehash\""
echo
echo "Next steps:"
echo "  ./setup.sh --bootstrap  # one-line destructive install with credentials output"
echo "  aida-setup --init       # initialize stack (if not running bootstrap)"
echo "  aida-start              # start services and Bridge"
echo "  AIDA_AUTH_PROFILE=user aida-setup-kanban --name \"My App\" --slug my-app"
echo "  aida-task-select --slug my-app"
echo "  AIDA_AUTH_PROFILE=ide aida-items-list --type issue"
echo "  aida-item-select --type issue --id 123"
echo "  aida-item --profile ide --comment \"Investigating now\""

separator

exit 0
