```mermaid
sequenceDiagram
    autonumber
    participant User as User
    participant Start as aida-start
    participant Compose as Docker Compose
    participant Back as taiga-back (gunicorn)
    participant Gwy as nginx gateway (:9000)
    participant Reconcile as identity.reconcile
    participant Bridge as aida-bridge

    User->>Start: run aida-start
    Start->>Start: ensure_env_with_port (TAIGA_* aligned)
    Start->>Compose: up -d (postgres, redis, rabbit, back, front, gateway)
    Compose-->>Start: containers started
    Start->>Gwy: wait / (200)
    Start->>Back: docker compose exec curl 127.0.0.1:8000/api/v1/auth (expect 401)
    Note over Start,Back: retry until backend auth endpoint responds

    Start->>Reconcile: reconcile_and_verify()
    Reconcile->>Back: manage.py ensure ide/scrum active + passwords
    Reconcile->>Gwy: POST /api/v1/auth (ide, scrum) -> tokens
    Gwy-->>Reconcile: 200 + tokens
    Reconcile->>Start: write .aida/auth.<profile>.json
    Note over Start,Reconcile: abort start if reconcile/auth fails

    Start->>Bridge: start in background
    Bridge-->>Start: /health 200
    Start-->>User: system ready
```