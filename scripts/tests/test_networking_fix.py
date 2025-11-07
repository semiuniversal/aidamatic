#!/usr/bin/env python3
import sys
import time
import requests

GATEWAY = "http://localhost:9000"


def check(url: str, expect: int = 200, timeout: float = 3.0) -> tuple[bool, int]:
    try:
        r = requests.get(url, timeout=timeout)
        return (r.status_code == expect), r.status_code
    except Exception:
        return (False, 0)


def main() -> int:
    ok_root, code_root = check(f"{GATEWAY}/", 200)
    ok_api, code_api = check(f"{GATEWAY}/api/v1", 200)

    print(f"Gateway /            → {'✅' if ok_root else '❌'} (HTTP {code_root})")
    print(f"Backend /api/v1      → {'✅' if ok_api else '❌'} (HTTP {code_api})")

    # Optional: brief retry window to catch just-started services
    if not (ok_root and ok_api):
        for _ in range(10):
            time.sleep(1)
            ok_root, code_root = check(f"{GATEWAY}/", 200)
            ok_api, code_api = check(f"{GATEWAY}/api/v1", 200)
            if ok_root and ok_api:
                break
        print("-- After retry --")
        print(f"Gateway /            → {'✅' if ok_root else '❌'} (HTTP {code_root})")
        print(f"Backend /api/v1      → {'✅' if ok_api else '❌'} (HTTP {code_api})")

    return 0 if (ok_root and ok_api) else 1


if __name__ == "__main__":
    raise SystemExit(main())
