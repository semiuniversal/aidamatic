## Taiga Gateway Auth Issue — Update

### Context
- Stack: Docker Compose (taiga-back, taiga-front, gateway/nginx, postgres, rabbit, redis)
- Migrations: rely on Taiga images’ entrypoints; no manual migrate
- Gateway: nginx on `localhost:9000`
- Temporary debug exposure: direct backend mapped to host `9001` for isolation

### Current Symptoms (after latest changes)
- In-container:
  - POST `/api/v1/auth` returns a valid token
  - GET `/api/v1/users/me` with `Authorization: Bearer <token>` returns 200 (OK)
- Via gateway (`localhost:9000`):
  - GET `/api/v1/users/me` with the exact same token returns 401 with body: `{"detail":"User not found","code":"user_not_found"}`
- Gateway logs are not showing per-request access lines despite server-level access_log configured to stdout (debug format). Response headers from the gateway show standard CORS headers but not our temporary debug headers.

### What We Tried
- Nginx forwarding adjustments:
  - Forward `Authorization` explicitly: `proxy_set_header Authorization $http_authorization;`
  - Preserve exact incoming host: `proxy_set_header Host $http_host;`
  - Forwarded host/port and site host context:
    - `proxy_set_header X-Forwarded-Host $http_host;`
    - `proxy_set_header X-Forwarded-Port $server_port;`
    - TEMP: `proxy_set_header X-Site-Host localhost:9000;`
  - `proxy_http_version 1.1` on `/api/`
- Temporary backend exposure at `9001`:
  - Direct curl to 9001 produced `400 Invalid HTTP Header: 'AUTHORIZATION'` (header quirk), so we validated in-container via Python requests instead (works: 200).
- Added logging/debugging in nginx:
  - Redirected error_log to `/dev/stderr` and access_log to `/dev/stdout`
  - Server-level `access_log /dev/stdout debug;` with a debug log_format including `$http_authorization` and upstream info
  - TEMP response headers from gateway (`X-Debug-Auth`, `X-Debug-Host`) for visibility
- Auth smoke script:
  - `scripts/tests/auth_smoke.sh` now fetches token in-container, verifies `/users/me` in-container (200), then calls gateway (still 401) and prints headers/body snippet.

### New Evidence
- Backend (gunicorn) accepts the token and returns the user (200) when called in-container. Token is valid.
- Gateway path yields 401 `user_not_found` with the same token. This strongly indicates a header/host/site-context mismatch at the reverse proxy boundary rather than credentials or DB state.
- Despite enabling access logging to stdout and adding debug headers, we do not see per-request access lines in `docker compose logs -f gateway`. This suggests either:
  - Access logs are not being emitted due to directive scope/override, or
  - We are not observing the right stream/context, or
  - The 401 originates upstream and nginx is not appending our added headers post-upstream response.

### Working Hypothesis
- Taiga appears to require consistent site/host context for token validation (e.g., `X-Site-Host` and forwarded host headers must match the configured domain/port used by the backend). The backend validates tokens in context of site host; mismatches lead to `user_not_found`.
- Our `docker/.env` TAIGA domain/URL values may not match the incoming host:port. Even with `X-Site-Host localhost:9000`, if the backend expects a different `TAIGA_SITES_DOMAIN`, validation can fail.

### Immediate Workaround
- Use the backend directly for API calls during development/testing:
  - Fetch token in-container (already automated by `auth_smoke.sh`)
  - Point client requests to `http://localhost:9001` (temporary direct mapping) or call via in-container Python (bypasses gateway) until the nginx path is corrected.

### Next Diagnostic Steps
1. Verify domain/port alignment in `docker/.env` (or `docker/env.example` baseline):
   - `TAIGA_SITES_DOMAIN`
   - `TAIGA_FRONTEND_URL`
   - `TAIGA_BACKEND_URL`
   - `TAIGA_EVENTS_URL`
   Ensure they include `:9000` and match the forwarded host we send via nginx.
2. Set `X-Site-Host` to the exact `TAIGA_SITES_DOMAIN` value (not just `localhost:9000`).
3. Ensure `proxy_set_header Host $http_host;` and `X-Forwarded-Host` flow consistently; avoid mixing `$host:$server_port` vs `$http_host`.
4. Confirm gateway access logging emits request lines:
   - Keep `access_log /dev/stdout debug;` at server scope
   - If still silent, add `access_log` inside the `/api/` location specifically
   - Tail logs: `docker compose -f docker/docker-compose.yml logs -f gateway`
5. If headers still do not reflect, capture packet-level traces or run a throwaway proxy (e.g., `nginx:alpine` with minimal config) to validate Authorization preservation.

### Minimal Repro (Automated)
- Run: `bash scripts/tests/auth_smoke.sh <password>`
  - Outputs 200 in-container for `/users/me`
  - Outputs 401 via gateway for `/users/me` with the same token

### Cleanup Plan (once fixed)
- Remove temporary backend port exposure (9001)
- Remove temporary `X-Site-Host` hardcode and debug headers
- Restore server access_log to standard `main` format
- Keep the `auth_smoke.sh` script for future regressions

### Status
- Blocked at gateway. Backend is healthy and accepts tokens. Need to align nginx forwarding and Taiga site-domain settings to resolve 401 `user_not_found` through the gateway.

---

### Addendum: Root Cause and Fix (Actionable)

- Root cause: Taiga validates tokens against the configured site domain. If `Host` at the backend differs from `settings.SITES['api']['domain']`, token lookup can fail with `user_not_found`.

- Align environment (update your `docker/.env` to match `docker/env.example`):
  - `TAIGA_SITES_SCHEME=http`
  - `TAIGA_SITES_DOMAIN=localhost:9000`
  - `TAIGA_URL=http://localhost:9000`
  - `TAIGA_FRONTEND_URL=http://localhost:9000`
  - `TAIGA_BACKEND_URL=http://localhost:9000`
  - `TAIGA_EVENTS_URL=ws://localhost:9000`

- Gateway `/api/` proxy headers (now applied):
  - Force exact site/host context: `Host`, `X-Forwarded-Host`, `X-Site-Host` set to `localhost:9000`
  - Forward proto/port: `X-Forwarded-Proto http`, `X-Forwarded-Port 9000`
  - Preserve `Authorization` header
  - Location-level access logging and a marker header for request tracing

- Verify backend expectation:
  - Inside taiga-back: `python - <<'PY'` to print `settings.SITES['api']['domain']` and confirm it matches `localhost:9000`.

- Quick host header switch (if needed, temporary):
  - Change `proxy_set_header Host` to the exact value backend expects (with or without port) and restart only the gateway.
