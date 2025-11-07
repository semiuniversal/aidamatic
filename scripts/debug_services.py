#!/usr/bin/env python3
import argparse
import requests

BASE = "http://localhost:9000"


def probe(path: str) -> None:
    url = f"{BASE}{path}"
    try:
        r = requests.get(url, timeout=3)
        print(f"GET {path} → HTTP {r.status_code}")
    except Exception as e:
        print(f"GET {path} → error: {e}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=BASE)
    args = p.parse_args(argv)

    global BASE
    BASE = args.base

    print(f"Probing base: {BASE}")
    probe("/")
    probe("/api/v1")
    probe("/api/v1/auth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
