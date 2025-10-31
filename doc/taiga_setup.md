### Taiga Local Setup (Docker)

This repo includes a local Taiga stack (NGINX gateway, frontend, backend, events, protected, Postgres, RabbitMQ, Redis).

#### 1) Prerequisites
- Docker and Docker Compose (v2)
- Ports available: 9000 (configurable)

#### 2) Configure environment
- Copy `docker/env.example` to `docker/.env`
- Edit values as needed. For local dev, defaults usually work.
- Set both SECRET_KEY and TAIGA_SECRET_KEY to long random strings (can be the same).

#### 3) Start services
```bash
scripts/taiga-up.sh
```
- Gateway will expose the UI at `http://localhost:9000`

#### 4) Stop services
```bash
scripts/taiga-down.sh
```

#### 5) Data persistence
- Postgres data: `taiga-db` named volume
- Media uploads: `taiga-media` named volume
- Static files: `taiga-static` named volume

#### 6) Notes
- Images are pinned to `latest` for convenience; for stability, pin to a known version.
- If the stack fails to start, review container logs with `docker compose -f docker/docker-compose.yml logs -f <service>`
- Initial user/bootstrap steps follow the official Taiga documentation for the image version you choose.

#### 7) API convenience scripts (dev)
- Set admin creds in `docker/.env`:
  - `TAIGA_ADMIN_USER=admin`
  - `TAIGA_ADMIN_PASSWORD=...`
- Get token:
  - `scripts/taiga-auth.sh`  (use `--refresh` to force refresh)
- Call API with token:
  - `scripts/taiga-api.sh GET /api/v1/projects`
  - `scripts/taiga-api.sh POST /api/v1/projects -H 'Content-Type: application/json' -d '{"name":"Demo"}'`

#### 8) Export/Import config
- Export the current project (by slug or id):
  - `aida-export --slug your-project-slug --output taiga-config.json --pretty`
- Dry-run import (prints plan):
  - `aida-import --input taiga-config.json`
- Apply import (creates project if missing):
  - `aida-import --input taiga-config.json --apply`
