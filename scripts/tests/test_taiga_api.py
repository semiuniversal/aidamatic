#!/usr/bin/env python3
import os
import sys
import json
import requests

GATEWAY = os.environ.get("TAIGA_BASE", "http://localhost:9000")
USER = os.environ.get("TAIGA_USER", "user")
PASS = os.environ.get("TAIGA_PASS", "ChangeMe123!")

def main() -> int:
    auth_url = f"{GATEWAY}/api/v1/auth"
    me_url = f"{GATEWAY}/api/v1/users/me"
    try:
        r = requests.post(auth_url, json={"type": "normal", "username": USER, "password": PASS}, timeout=5)
        print(f"POST /api/v1/auth → HTTP {r.status_code}")
        if r.status_code != 200:
            print(r.text)
            return 1
        token = (r.json() or {}).get("auth_token")
        if not token:
            print("No auth_token in response")
            return 1
        h = {"Authorization": f"Bearer {token}"}
        m = requests.get(me_url, headers=h, timeout=5)
        print(f"GET /api/v1/users/me → HTTP {m.status_code}")
        if m.status_code == 200:
            print(json.dumps(m.json(), indent=2))
            return 0
        print(m.text)
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
