#!/bin/bash

set -e

separator() {
    printf -- '------------------------------------------------------------\n'
}

echo "Starting project environment setup..."
separator

# Step 1: Check if 'uv' command is available
if ! command -v uv >/dev/null 2>&1; then
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
else
    echo "'uv' command found."
fi

separator

# Step 2: Check if virtual environment exists, create if missing
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

# Step 3: Activate the virtual environment
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

# Step 4: Verify Python interpreter presence in the virtual environment
PYTHON_BIN=".venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "Error: Python interpreter not found at '$PYTHON_BIN'."
    echo "Try deleting '.venv' and rerunning the setup."
    exit 1
fi

separator

# Step 5: Install dependencies (editable mode)
echo "Installing dependencies in editable mode with 'uv pip install -e .'..."
uv pip install -e . || {
    echo "Dependency installation failed."
    exit 1
}
echo "Dependencies installed successfully."

separator

# Final message
echo "Setup complete! 🎉"
echo "You can now use 'python' inside the activated virtual environment to run commands."
echo "If you open a new terminal session, remember to activate the environment first by running:"
echo "  source .venv/bin/activate"
echo "Suggestion for convenience, if you want to run setup and activate in one command:"
echo "create a bash alias for running setup and activate:"
echo " alias setup='./setup.sh && source .venv/bin/activate'"

separator

exit 0
