#!/usr/bin/env python3
"""
Test starting the Bridge server to see what's wrong
"""

import subprocess
import sys
import os
from pathlib import Path


def test_bridge_startup():
    """Test different ways to start the Bridge server"""

    print("🧪 Testing Bridge Server Startup")
    print("=" * 40)

    # Method 1: Try the original command from aidastart.py
    print("1. Testing original command: python -m aidamatic.bridge.app")
    try:
        result = subprocess.run([sys.executable, "-m", "aidamatic.bridge.app"],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("  ✅ SUCCESS - Bridge started")
            print(f"  Output: {result.stdout[:200]}")
        else:
            print(f"  ❌ FAILED - Return code: {result.returncode}")
            print(f"  Error: {result.stderr[:500]}")
    except FileNotFoundError:
        print("  ❌ FAILED - Module 'aidamatic.bridge.app' not found")
    except subprocess.TimeoutExpired:
        print("  ⏰ TIMEOUT - Bridge started but didn't exit (expected)")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")

    print("\n2. Testing alternative: python -m src.aidamatic.bridge.app")
    try:
        result = subprocess.run([sys.executable, "-m", "src.aidamatic.bridge.app"],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("  ✅ SUCCESS - Bridge started")
            print(f"  Output: {result.stdout[:200]}")
        else:
            print(f"  ❌ FAILED - Return code: {result.returncode}")
            print(f"  Error: {result.stderr[:500]}")
    except FileNotFoundError:
        print("  ❌ FAILED - Module 'src.aidamatic.bridge.app' not found")
    except subprocess.TimeoutExpired:
        print("  ⏰ TIMEOUT - Bridge started but didn't exit (expected)")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")

    print("\n3. Testing direct import: python -c 'import aidamatic.bridge.app'")
    try:
        result = subprocess.run([sys.executable, "-c", "import aidamatic.bridge.app"],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("  ✅ SUCCESS - Module can be imported")
        else:
            print(f"  ❌ FAILED - Import error")
            print(f"  Error: {result.stderr[:500]}")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")

    print("\n4. Checking Python path and current directory")
    print(f"  Current directory: {Path.cwd()}")
    print(f"  Python executable: {sys.executable}")
    print(f"  Python path: {sys.path[:3]}...")  # Show first 3 entries

    # Check if src directory exists
    src_path = Path("src")
    if src_path.exists():
        print(f"  ✅ src/ directory exists")
        bridge_app = src_path / "aidamatic" / "bridge" / "app.py"
        if bridge_app.exists():
            print(f"  ✅ Bridge app exists at: {bridge_app}")
        else:
            print(f"  ❌ Bridge app NOT found at: {bridge_app}")
    else:
        print(f"  ❌ src/ directory NOT found")

    print("\n5. Testing with explicit PYTHONPATH")
    try:
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path.cwd())
        result = subprocess.run([sys.executable, "-c", "import aidamatic.bridge.app; print('Import successful')"],
                              env=env, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("  ✅ SUCCESS - Import works with PYTHONPATH")
        else:
            print(f"  ❌ FAILED - Import still fails")
            print(f"  Error: {result.stderr[:500]}")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")


if __name__ == "__main__":
    test_bridge_startup()
