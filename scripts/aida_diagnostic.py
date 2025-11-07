#!/usr/bin/env python3
import subprocess
import requests
import shutil

COMPOSE = ["docker", "compose", "-f", "docker/docker-compose.yml"]
BASE = "http://localhost:9000"


def run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 1, "", str(e)


def http_get(url: str, timeout: float = 3.0) -> int:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code
    except Exception:
        return 0


def main() -> int:
    print("== Docker diagnostics ==")
    rc, out, err = run(["docker", "info"])
    print(f"docker info → rc={rc}")
    print("--")

    print("== Compose ps ==")
    rc, out, err = run(COMPOSE + ["ps"])
    print(out.strip())
    print("--")

    print("== Endpoints ==")
    code_root = http_get(f"{BASE}/")
    code_api = http_get(f"{BASE}/api/v1")
    code_auth_get = http_get(f"{BASE}/api/v1/auth")
    print(f"GET /             → {code_root}")
    print(f"GET /api/v1       → {code_api}")
    print(f"GET /api/v1/auth  → {code_auth_get} (expect 405)")
    print("--")

    print("== Recent logs (gateway & back) ==")
    rc, out, err = run(COMPOSE + ["logs", "--tail", "50", "gateway", "taiga-back"]) 
    print(out.strip())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
