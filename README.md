# aidamatic

Local AI task orchestration with Taiga and a modal, per-request Bridge.

## Overview
AIDA helps you run AI-powered coding sessions as a focused, auditable workflow. It runs Taiga (an open‑source project tracker) locally in Docker and exposes a localhost Bridge so different actors (you, your IDE agent, a scrum agent) can operate on the current task using per‑request identities. No internet exposure, no team server — just a simple local stack.

```mermaid
flowchart LR
  U[User (human)] -->|CLI --profile user| B[Bridge (127.0.0.1:8787)]
  I[IDE agent] -->|CLI --profile ide| B
  S[Scrum agent] -->|CLI --profile scrum| B
  B -->|REST| T[(Taiga on Docker)]
```

## What this is / is not

- This is: a single-user, localhost-only helper for AI-enabled development.
  - Local Taiga + a small Bridge to manage tasks, comments, status, and context.
  - No implicit repo scanning; context is explicit (.aida/*, opt-in docs).
  - Designed for one operator (you) guiding AI work with minimal overhead.
- This is not: a team/collaboration or production system.
  - No multi-user sessions, auth, or external exposure.
  - Not hardened for internet access; do not run on public interfaces.

## Why AIDA (Problem → Solution → Value)

- Problem: AI coding sessions drift; long chats lose the plot. Developers juggle todo files and ad‑hoc notes with no clear, auditable flow.
- Solution: Treat the AI as a task executor. Use Taiga as the source of truth and a local “Scrum Master” bridge to focus work on one item, enforce templates and acceptance criteria, and log actions.
- Value:
  - Structured flow (Kanban) with optional short “focus cycles” for phasing
  - One clear task at a time; reduce context reset
  - Automatic status/comments with local audit trail (`.aida/outbox/*`)
  - IDE‑agnostic (CLI/HTTP), provider‑agnostic (Anthropic/OpenAI later)

Who it’s for:
- Product-minded developer guiding AI work locally, wanting explicit scope, acceptance criteria, and quick iteration without team‑scale tooling.

More context: see `doc/aida_v2.md` for the product brief and developer guide.

## Prerequisites

- OS: Linux or macOS; Windows via WSL2 (run all commands from a WSL shell)
- Docker Desktop with Docker Compose enabled (WSL2 integration on Windows)
- Python 3.10+ with pip
- Optional: ANTHROPIC_API_KEY for the smoke test (not required for core features)

## Quick start (first install)

1. **Clone this repo** and enter the folder.
2. **Run the one-line bootstrap** (creates the virtual env, installs dependencies, resets Taiga, starts everything):
   ```bash
   ./setup.sh --bootstrap
   ```
   - Expect this to take 3–5 minutes on a cold start. You will see live progress (for example `Waiting for API... (elapsed 02m15s)`).
   - Do not interrupt until you see `Bootstrap complete in 0XmYYs` and the printed Taiga credentials.
   - The bootstrap provisions three accounts (`user`, `ide`, `scrum`) and leaves the stack running with the Bridge listening on `127.0.0.1:8787`.
   - You can supply `AIDA_BOOTSTRAP_ADMIN_PASS=...` to skip the password prompt; otherwise you’ll be asked once (press Enter to auto-generate).
   - The human account credentials are shown at the end (`user` / chosen password). AI identities live in `.aida/identities.json`.
3. **Activate the virtual environment** (bootstrap creates `.venv`):
   ```bash
   source .venv/bin/activate
   ```

That’s it—you can now use the CLI helpers below. Every subsequent terminal session only needs `source .venv/bin/activate` followed by `aida-start`.

### What you’ll see during bootstrap

- `Waiting for gateway/API/auth ... (elapsed mm:ss)` – automatic readiness checks. The Taiga containers need a few minutes after migrations.
- `Applying backend grace period` – a final 15‑second buffer before identities are reconciled.
- `AIDA start` output – once this finishes and prints `AIDA is ready`, the system is live.

If bootstrap fails, revisit Docker Desktop state, rerun `./setup.sh --bootstrap`, and check `.aida/bridge.log` for Bridge issues.

## Daily usage

```bash
# Start services + Bridge (takes a few minutes, blocks until ready)
aida-start

# Stop everything
aida-stop

# Restart quickly
aida-restart
```

- `aida-start` is safe to rerun; it waits for Taiga and the auth endpoint before reconciling identities and launching the Bridge. Progress messages continue to show elapsed time.
- `aida-stop` stops both the Bridge and the Taiga Docker stack.

> Identities are modal. Bridge CLIs need `--profile user|ide|scrum`; Taiga helpers can use `AIDA_AUTH_PROFILE=<profile>`. See [Identities and profiles](#identities-and-profiles).

### Optional: fresh reset mid-project

If you need a destructive reset later (drop volumes, recreate identities) run:
```bash
aida-setup --reset --force --yes
# then
aida-start
```
Only use the reset when you’re okay with losing the Taiga database.

## Manual installation (advanced)

You rarely need this now that `./setup.sh --bootstrap` handles everything, but the steps remain available for power users:

1. Create/activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install in editable mode (`uv` or `pip`):
   ```bash
   uv pip install -e .  # or: pip install -e .
   ```
3. Copy `docker/env.example` to `docker/.env` and tweak if you need custom ports/domains.
4. Start the stack with `aida-bootstrap` (reset + start) or `aida-start` (no reset).

## Troubleshooting wait times

- Long pauses (~3–5 minutes) during `./setup.sh --bootstrap` or `aida-start` are normal. Look for the elapsed timers; as long as they’re updating, the system is still preparing migrations.
- If the wait exceeds ~6 minutes or you see a timeout, run `docker compose -f docker/docker-compose.yml logs taiga-back` to ensure migrations aren’t failing.
- For Bridge issues, check `.aida/bridge.log` after `aida-start` finishes.
- If Docker Desktop was restarted, rerun `aida-start`; it will reconcile identities again automatically.

## Advanced / Admin

### Taiga stack (Docker)

These are advanced/admin-oriented helpers used by `aida-setup` and `aida-start`. Most users won’t need them directly.

```bash
cp docker/env.example docker/.env
# Edit docker/.env if needed (ports/hostnames)

aida-start
# later: aida-stop
```

## Identities and profiles

- user: human account (admin privileges). Credentials entered once; token persisted; password not stored locally by default.
- ide: IDE agent (non-human). Auto-provisioned with random password; credentials stored locally in `.aida/identities.json`.
- scrum: Scrum Master agent (non-human). Auto-provisioned with random password; credentials stored locally.

Usage rules
- Bridge is modal per request. Pass `--profile user|ide|scrum` on CLIs (sends `X-AIDA-Profile`).
- Direct Taiga CLIs can use `AIDA_AUTH_PROFILE=<profile>`.
- Legacy `developer` profile is mapped to `ide`.

## Basic workflow (example)

```bash
# 1) Initialize and start services (non-destructive)
aida-setup --init
aida-start

# 2) Project creation is automatic in bootstrap (S4) using the repo folder name (Kanban enabled).

# 3) Select the project for this workspace
aida-task-select --slug my-app

# 4) Work on items as the IDE agent
# Use the Bridge UI/workflows (VS Code integration) rather than CLI item operations.
# The following CLI utilities have been removed to reduce duplication: items-list, item-select, item, task-next, sync.
```

## AIDA Bridge (local HTTP + CLI)

The Bridge listens on 127.0.0.1:8787 and is started by `aida-start`. All Bridge requests are identity-modal: specify who is acting via `--profile user|ide|scrum`. The CLIs add the header `X-AIDA-Profile` for you.

```bash
# Current assignment (local)
# Item/document/chat CLI utilities have been removed in favor of Bridge and future IDE integration.
```

Advanced: You may call HTTP endpoints directly and pass `X-AIDA-Profile` yourself, but the CLIs are preferred.

### Auth and API convenience

Profiles authenticate independently and persist tokens locally in `.aida/auth.<profile>.json`.

```bash
# Authenticate non-human profiles (no prompts)
# Authentication and project reconciliation are handled by `aida-bootstrap` during S4 via python-taiga.
# Manual auth/profile commands have been removed to prevent drift.
```

## Project selection & listing

```bash
# Identity-scoped listing with TYPE (direct to Taiga)
# Uses AIDA_AUTH_PROFILE or .aida/auth.json if present
AIDA_AUTH_PROFILE=ide aida-projects-list

# Include archived or filter by tag
AIDA_AUTH_PROFILE=ide aida-projects-list --all
AIDA_AUTH_PROFILE=ide aida-projects-list --tag aida:work

# Select a project for the current session (writes .aida/assignment.json)
# Project selection happens implicitly via repo folder name during bootstrap; manual selection CLI removed.
```

## Items listing & selection

```bash
# List items in the selected project (default: issues, assigned to you optional)
# Use the Bridge UI to browse and select items; CLI listing removed.

# Select an item by id or ref
aida-item-select --type issue --id 123
# or
 aida-item-select --type issue --ref 45
```

## Create a new Kanban project

```bash
# Create a fresh Kanban project from the current folder (requires a profile with permissions)
AIDA_AUTH_PROFILE=user aida-setup-kanban --name "My App" --slug my-app
# Members 'ide' and 'scrum' are auto-added if present in identities
```

### Reset/Clean helpers (CLI)

```bash
# Full reset (destroys Taiga data and local state if --purge-local)
# Prompts for the human 'user' (admin privileges). Non-human accounts are auto-provisioned.
aida-setup --reset --force

# Low-level Taiga reset (advanced):
#   aida-bootstrap  # run with --bootstrap to reset + start

# Hard clean (data loss)
# Use docker compose down -v manually if required; destructive cleans are not exposed as CLI.
```

Data loss explained:
- Removes Docker volumes: taiga-db, taiga-media, taiga-static
- Wipes all Taiga data: users, projects, items, comments, attachments/media, and configuration stored in volumes
- With --purge-local: also deletes local AIDA state in this repo (.aida/) and .taiga_token

## Export / Import project config

```bash
# Export current project (pick by slug or id)
# Project export/import CLI removed. Migration utilities will be exposed via Bridge APIs in a future release.
```

## Smoke test Anthropic

```bash
aida-anthropic-smoke
```

## Documentation

- Identities, profiles, and IDE integration: `doc/ide_integration.md`
- Kanban flow and focus cycles: `doc/estimation_and_cycles.md`
- Product brief and implementation context: `doc/aida_v2.md`
