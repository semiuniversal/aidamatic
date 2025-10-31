<#
.SYNOPSIS
    Setup script for Python project environment using uv, with preemptive deletion of `.venv`.

.DESCRIPTION
    Deletes `.venv` if it exists, installs 'uv' if missing, creates a new virtual environment, activates it,
    installs project dependencies, and provides user-friendly messages.
#>

function Write-Seperator {
    Write-Host ('-'*60) -ForegroundColor DarkGray
}

Write-Host "Starting project environment setup..." -ForegroundColor Cyan
Write-Seperator

# --- Step 1: Check if 'uv' command exists; install if not ---
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "'uv' command not found. Installing uv..." -ForegroundColor Yellow

    try {
        powershell -ExecutionPolicy ByPass -Command "Invoke-Expression (Invoke-RestMethod https://astral.sh/uv/install.ps1)"
        $uvInstallPath = "$env:USERPROFILE\.local\bin"

        if (-not ($env:PATH -like "*$uvInstallPath*")) {
            $env:PATH = "$uvInstallPath;$env:PATH"
            Write-Host "Temporarily added uv install path to PATH for this session." -ForegroundColor Green
        }

        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            Write-Warning "'uv' was installed but is not available in the current PowerShell session."
            Write-Warning "Please CLOSE this PowerShell window and OPEN a NEW ONE to continue."
            Write-Warning "After restarting PowerShell, rerun this script (or run setup steps manually)."
            exit 0
        } else {
            Write-Host "'uv' installed successfully!" -ForegroundColor Green
        }
    }
    catch {
        Write-Error "An error occurred during 'uv' installation: $_"
        Write-Host "Please install 'uv' manually using: irm https://astral.sh/uv/install.ps1 | iex" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "'uv' command is already installed." -ForegroundColor Green
}

Write-Seperator

# --- Step 2: Preemptively remove existing .venv virtual environment ---
if (Test-Path ".venv") {
    Write-Host "Existing '.venv' directory found. Removing to start fresh..." -ForegroundColor Yellow
    try {
        Remove-Item -Recurse -Force -LiteralPath ".venv"
        Write-Host "Deleted existing '.venv' directory." -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to remove existing '.venv': $_"
        exit 1
    }
} else {
    Write-Host "No existing '.venv' directory found. Proceeding..."
}

Write-Seperator

# --- Step 3: Create new virtual environment ---
Write-Host "Creating virtual environment with 'uv venv'..." -ForegroundColor Cyan
uv venv
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create virtual environment. Please check uv installation."
    exit 1
}
Write-Host "Virtual environment created successfully." -ForegroundColor Green

Write-Seperator

# --- Step 4: Activate the virtual environment with fallback paths ---
$activateScript = Join-Path -Path ".venv" -ChildPath "Scripts\Activate.ps1"

if (-not (Test-Path $activateScript)) {
    $activateScript = Join-Path -Path ".venv" -ChildPath "bin/Activate.ps1"
}

if (Test-Path $activateScript) {
    Write-Host "Activating the virtual environment from path: $activateScript"
    . $activateScript
    Write-Host "Virtual environment activated." -ForegroundColor Green
} else {
    Write-Error "Could not find activation script at expected paths:
    .venv\Scripts\Activate.ps1
    .venv/bin/Activate.ps1"
    exit 1
}

Write-Seperator

# --- Step 5: Verify python interpreter inside venv ---
$pythonExe = Join-Path -Path ".venv\Scripts" -ChildPath "python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Error "Python interpreter not found at '$pythonExe'. Virtual environment creation may have failed."
    exit 1
}

Write-Seperator

# --- Step 6: Install dependencies ---
Write-Host "Installing dependencies in editable mode using 'uv pip install -e .'..." -ForegroundColor Cyan
uv pip install -e .
if ($LASTEXITCODE -ne 0) {
    Write-Error "Dependency installation failed."
    exit 1
}

Write-Host "Dependencies installed successfully." -ForegroundColor Green

Write-Seperator

# --- Final message ---
Write-Host "Setup complete! 🎉" -ForegroundColor Green
Write-Host "Use 'python' inside this environment to run commands."
Write-Host "Remember: on new PowerShell sessions, activate the venv by running:" -ForegroundColor Yellow
Write-Host "    . .venv\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Seperator

exit 0
