#!/usr/bin/env python3
import time
import subprocess
import requests

COMPOSE = ["docker", "compose", "-f", "docker/docker-compose.yml"]
BASE = "http://localhost:9000"


def http_ok(url: str, expect: int = 200, timeout: float = 3.0) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == expect
    except Exception:
        return False


def main() -> int:
    print("Bringing up services (detached)...")
    subprocess.run(COMPOSE + ["up", "-d"], check=False)

    start = time.time()
    deadline = start + 900

    print("TX1: Gateway / (200)")
    while time.time() < deadline and not http_ok(f"{BASE}/", 200):
        time.sleep(1)
    ok1 = http_ok(f"{BASE}/", 200)
    print(f"→ {'OK' if ok1 else 'TIMEOUT'}")

    print("TX2: API /api/v1 (200)")
    while time.time() < deadline and not http_ok(f"{BASE}/api/v1", 200):
        time.sleep(1)
    ok2 = http_ok(f"{BASE}/api/v1", 200)
    print(f"→ {'OK' if ok2 else 'TIMEOUT'}")

    print("If both TX1 and TX2 are OK, run aida-start to reconcile and launch Bridge.")
    print("Diagnostics: run scripts/aida_diagnostic.py and review log.log if issues persist.")
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
