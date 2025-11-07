#!/usr/bin/env python3
"""
Quick test: Is the Bridge server actually running?
"""

import requests
import time


def test_bridge_server():
    """Test Bridge server directly"""
    print("🧪 Testing Bridge server at http://localhost:8787")

    # Test different potential endpoints
    endpoints = [
        "/health",
        "/",
        "/api/health",
        "/status",
        "/ping"
    ]

    for endpoint in endpoints:
        try:
            url = f"http://localhost:8787{endpoint}"
            print(f"Testing: {url}")
            response = requests.get(url, timeout=5)
            print(f"  ✅ Response: {response.status_code} - {response.text[:100]}")
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Connection failed - server not running?")
        except requests.exceptions.Timeout:
            print(f"  ⏰ Timeout - server not responding")
        except Exception as e:
            print(f"  ⚠️  Error: {e}")

        time.sleep(1)

    # Check if port is even open
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 8787))
        sock.close()

        if result == 0:
            print("✅ Port 8787 is open (something is listening)")
        else:
            print("❌ Port 8787 is closed (Bridge server not running)")
    except Exception as e:
        print(f"⚠️  Port check error: {e}")


if __name__ == "__main__":
    test_bridge_server()
