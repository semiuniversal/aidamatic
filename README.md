# aidamatic

AIDA (AI Delivery Automation) - Scrum Master Agent orchestration for Taiga.

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

## Platform support

- Supported: Linux and macOS.
- Windows: supported via WSL2 only. Use Docker Desktop with WSL integration enabled and run all commands from a WSL shell.
- Native Windows shells (PowerShell/CMD) are not supported for the scripts/CLIs in this repo.

## Quick start

```bash
aida-start
```

This wizard will bring up Taiga, prompt for credentials, bind your identity, create/select a Kanban project, and start the AIDA Bridge.

Control:
- aida-stop: stops the bridge and Taiga stack
- aida-restart: stop then run the wizard again


## Setup

1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2. Install in editable mode (supports `uv` or `pip`)

```bash
# Using uv
uv pip install -e .

# Or using pip
pip install -e .
```

3. Configure environment (dev)

```bash
# Create a .env file and add your keys when ready
# Example:
# ANTHROPIC_API_KEY=sk-ant-...
```

## Taiga stack (Docker)

Quick start (see `doc/taiga_setup.md` for details):

```bash
cp docker/env.example docker/.env
# Edit docker/.env and set at least:
#  SECRET_KEY, TAIGA_SECRET_KEY (long random strings)
#  TAIGA_ADMIN_PASSWORD (for token scripts)

aida-taiga-up
# later: aida-taiga-down
```

## AIDA Bridge (local HTTP + CLI)

```bash
# Start the bridge on localhost:8787
aida-bridge
# Health
curl -s http://127.0.0.1:8787/health
# Projects (scoped)
curl -s 'http://127.0.0.1:8787/projects'
# Current assignment
curl -s 'http://127.0.0.1:8787/task/current'
# Comment / Status via CLI wrappers
aida-task-comment --text "Investigating now"
aida-task-status --to in_progress
# History
curl -s 'http://127.0.0.1:8787/task/history'

# Sync outbox to Taiga (requires status-map.json)
aida-sync
# Or via HTTP (dry-run first)
curl -s -X POST 'http://127.0.0.1:8787/sync/outbox?dry_run=true'
```

## Auth and API convenience

```bash
# Fetch and cache a token (reads docker/.env)
aida-taiga-auth --refresh

# Call the Taiga API with the cached token
aida-taiga-api GET /api/v1/projects
```

## Project selection & listing

```bash
# Identity-scoped, active-only listing (default)
aida-projects-list

# Include archived or filter by tag
aida-projects-list --all
 aida-projects-list --tag aida:work

# Select a project for the current IDE session (writes .aida/assignment.json)
aida-task-select --slug your-project-slug
```

## Items listing & selection

```bash
# List items in the selected project (default: issues, assigned to you optional)
aida-items-list --type issue --assigned-to-me

# Select an item by id or ref
aida-item-select --type issue --id 123
# or
 aida-item-select --type issue --ref 45
```

## Create a new Kanban project

```bash
# Create a fresh Kanban project from the current folder (admin token required)
aida-setup-kanban --name "My App" --slug my-app
```

## Reset/Clean helpers (CLI)

```bash
# You can pass credentials via flags (or env):
#   aida-taiga-reset --admin-user "Your Name" --admin-email you@example.com --admin-pass 'your-strong-password'
# If omitted, user/email fall back to git/OS identity; --admin-pass (or ADMIN_PASS) is required.

aida-taiga-reset --admin-pass 'your-strong-password'

# Hard clean (data loss) without restart)
aida-taiga-clean --force [--purge-local]
```

Data loss explained:
- Removes Docker volumes: taiga-db, taiga-media, taiga-static
- Wipes all Taiga data: users, projects, items, comments, attachments/media, and configuration stored in volumes
- With --purge-local: also deletes local AIDA state in this repo (.aida/) and .taiga_token

## Export / Import project config

```bash
# Export current project (pick by slug or id)
aida-export --slug your-project-slug --output taiga-config.json --pretty

# Dry-run import (prints plan)
aida-import --input taiga-config.json

# Apply import (creates project if missing)
aida-import --input taiga-config.json --apply
```

## Smoke test Anthropic

```bash
aida-anthropic-smoke
```

## Documentation

- Taiga setup and usage: `doc/taiga_setup.md`
- Agent architecture and provider guidance: `doc/scrum_master_agent_intelligence.md`
- Product brief and implementation context: `doc/aida_v2.md`
