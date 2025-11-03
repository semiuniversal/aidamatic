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

## Quick start

```bash
aida-setup --init
#aida-start starts services and the local Bridge (non-interactive)
aida-start
```

- aida-setup --init: non-destructive initialization that starts Taiga and binds cached identities.
- aida-start: starts services and the AIDA Bridge in the background. No prompts.

Control:
- aida-stop: stops the Bridge and Taiga stack
- aida-restart: stop then start again

Note on identities: All operations are modal by profile. Pass `--profile user|ide|scrum` on CLIs that hit the Bridge; or set `AIDA_AUTH_PROFILE` for direct Taiga CLIs. See “Identities and profiles”.

## Installation

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

Tip: define a reusable alias to run setup then activate the venv in your current shell session:

```bash
alias av="./setup.sh && source .venv/bin/activate && rehash"
```

Then you can simply run `av` next time you open a terminal in this project (or any similar Python project).

3. Configure environment (dev)

```bash
# Create a .env file and add your keys when ready
# Example:
# ANTHROPIC_API_KEY=sk-ant-...
```

## Advanced / Admin

### Taiga stack (Docker)

These are advanced/admin-oriented helpers used by `aida-setup` and `aida-start`. Most users won’t need them directly.

```bash
cp docker/env.example docker/.env
# Edit docker/.env if needed (ports/hostnames)

aida-taiga-up
# later: aida-taiga-down
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

# 2) Create a Kanban project (human user)
AIDA_AUTH_PROFILE=user aida-setup-kanban --name "My App" --slug my-app

# 3) Select the project for this workspace
aida-task-select --slug my-app

# 4) Work on items as the IDE agent
AIDA_AUTH_PROFILE=ide aida-items-list --type issue
# pick one (by id or ref):
aida-item-select --type issue --id 123

# 5) Operate via Bridge (per request profile)
aida-item --profile ide --comment "Investigating now"
aida-item --profile ide --status to=in_progress

aida-task-next --profile ide

aida-sync
```

## AIDA Bridge (local HTTP + CLI)

The Bridge listens on 127.0.0.1:8787 and is started by `aida-start`. All Bridge requests are identity-modal: specify who is acting via `--profile user|ide|scrum`. The CLIs add the header `X-AIDA-Profile` for you.

```bash
# Current assignment (local)
aida-item-select --type issue --id 123

# Add a comment as the IDE agent
#aida-item consolidates comment and status
 aida-item --profile ide --comment "Investigating now"

# Change status as the IDE agent
 aida-item --profile ide --status to=in_progress

# Suggest next item for a profile
 aida-task-next --profile ide

# Sync outbox events to Taiga
 aida-sync

# Docs inbox (local)
# List docs (profile required for audit trail)
 aida-doc --profile ide --list
# Add a text note
 aida-doc --profile ide --text "Design notes" --tag brief --name notes.md
# Add a file
 aida-doc --profile ide --file ./mockup.png --tag ui

# Chat skeleton (local)
 aida-chat --profile user --send "Kick off grooming for Docs inbox"
 aida-chat --profile user --thread --tail 20
```

Advanced: You may call HTTP endpoints directly and pass `X-AIDA-Profile` yourself, but the CLIs are preferred.

### Auth and API convenience

Profiles authenticate independently and persist tokens locally in `.aida/auth.<profile>.json`.

```bash
# Authenticate non-human profiles (no prompts)
TAIGA_ADMIN_USER=ide TAIGA_ADMIN_PASSWORD='your-generated-pass' aida-taiga-auth --profile ide --switch-user
TAIGA_ADMIN_USER=scrum TAIGA_ADMIN_PASSWORD='your-generated-pass' aida-taiga-auth --profile scrum --switch-user

# Authenticate human user once, if desired (not stored)
aida-taiga-auth --profile user --switch-user

# Call Taiga API directly as a profile (advanced)
AIDA_AUTH_PROFILE=ide aida-taiga-api GET /api/v1/projects
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
#   aida-taiga-reset --admin-user "your_user" --admin-email you@example.com --admin-pass 'strong'

# Hard clean (data loss)
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

- Identities, profiles, and IDE integration: `doc/ide_integration.md`
- Kanban flow and focus cycles: `doc/estimation_and_cycles.md`
- Product brief and implementation context: `doc/aida_v2.md`
