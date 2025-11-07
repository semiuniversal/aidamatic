#!/usr/bin/env python3
"""
Quick fix: Start the Bridge server manually with correct paths
"""

import subprocess
import sys
import os
import time
import requests
from pathlib import Path


def start_bridge_fixed():
    """Start the Bridge server with proper paths"""

    print("🚀 Starting AIDA Bridge Server (Fixed)")
    print("=" * 40)

    # Set up environment
    env = os.environ.copy()
    env.setdefault('PYTHONPATH', str(Path.cwd()))

    # Try different startup methods (prefer installed module path)
    startup_commands = [
        [sys.executable, "-m", "aidamatic.bridge.app"],
        [sys.executable, "src/aidamatic/bridge/app.py"],
        [sys.executable, "-c", "from aidamatic.bridge.app import run; run()"],
    ]

    for i, cmd in enumerate(startup_commands, 1):
        print(f"\n{i}. Trying: {' '.join(cmd)}")
        try:
            # Start the process
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            print(f"   Process started with PID: {proc.pid}")

            # Wait a moment for startup
            time.sleep(3)

            # Check if it's still running
            if proc.poll() is None:
                print("   ✅ Process is still running")

                # Test if the server is responding
                try:
                    response = requests.get("http://localhost:8787/health", timeout=5)
                    if response.status_code == 200:
                        print("   🎉 SUCCESS! Bridge server is responding")
                        print("   Bridge available at: http://localhost:8787")
                        return proc
                    else:
                        print(f"   ⚠️  Server responding but health check failed: {response.status_code}")
                except requests.exceptions.ConnectionError:
                    print("   ⚠️  Server process running but not accessible")
                except requests.exceptions.Timeout:
                    print("   ⚠️  Server responding but slow")
            else:
                print("   ❌ Process exited immediately")
                stdout, stderr = proc.communicate()
                if stdout:
                    print(f"   stdout: {stdout[:200]}")
                if stderr:
                    print(f"   stderr: {stderr[:200]}")

        except Exception as e:
            print(f"   ❌ Failed to start: {e}")

    print("\n❌ All startup methods failed")
    return None


def test_bridge_endpoints(bridge_proc):
    """Test Bridge server endpoints once it's running"""
    if not bridge_proc:
        return

    print("\n🧪 Testing Bridge Endpoints")
    print("-" * 30)

    endpoints = [
        "/health",
        "/",
        "/api/status",
    ]

    for endpoint in endpoints:
        try:
            response = requests.get(f"http://localhost:8787{endpoint}", timeout=5)
            print(f"  ✅ {endpoint}: {response.status_code}")
            if response.status_code == 200:
                print(f"     Response: {response.text[:100]}...")
        except Exception as e:
            print(f"  ❌ {endpoint}: {e}")


def main() -> int:
    print("This script will attempt to start the AIDA Bridge server manually")
    print("If successful, it will keep running until you stop it (Ctrl+C)")
    print()

    bridge_proc = start_bridge_fixed()

    if bridge_proc:
        test_bridge_endpoints(bridge_proc)
        print("\n✅ Bridge is running! Press Ctrl+C to stop.")
        try:
            bridge_proc.wait()  # Keep running
        except KeyboardInterrupt:
            print("\n🛑 Stopping Bridge server...")
            bridge_proc.terminate()
            bridge_proc.wait()
            print("✅ Bridge server stopped")
        return 0
    else:
        print("\n❌ Could not start Bridge server")
        print("Check the error messages above for troubleshooting")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
