# aidamatic

AIDA - Scrum Master Agent orchestration for Taiga.

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

---

## Taiga stack (Docker)

Quick start (see `doc/taiga_setup.md` for details):

```bash
cp docker/env.example docker/.env
# Edit docker/.env and set at least:
#  SECRET_KEY, TAIGA_SECRET_KEY (long random strings)
#  TAIGA_ADMIN_PASSWORD (for token scripts)

bash scripts/taiga-up.sh
# later: bash scripts/taiga-down.sh
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
scripts/taiga-auth.sh --refresh

# Call the Taiga API with the cached token
scripts/taiga-api.sh GET /api/v1/projects
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

# List items in the selected project (default: issues, assigned to you optional)
aida-items-list --type issue --assigned-to-me

# Select an item by id or ref
aida-item-select --type issue --id 123
# or
 aida-item-select --type issue --ref 45
```

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

## Configuration notes

- Taiga base URL: `TAIGA_BASE_URL` (defaults to `http://localhost:9000`)
- Taiga image tag pinning: set `TAIGA_TAG` in `docker/.env` (defaults to `latest`)
- Tokens: CLI uses `TAIGA_TOKEN` if present; otherwise calls `scripts/taiga-auth.sh`

## Documentation

- Taiga setup and usage: `doc/taiga_setup.md`
- Agent architecture and provider guidance: `doc/scrum_master_agent_intelligence.md`
