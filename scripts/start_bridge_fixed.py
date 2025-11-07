#!/usr/bin/env python3
"""
Fixed bridge startup script with correct module paths for src-layout project.
This script tries multiple methods to start the AIDA Bridge server.
"""

import subprocess
import sys
import os
import time
import requests
from pathlib import Path

def start_bridge_fixed():
    """Start the AIDA Bridge server using corrected module paths."""
    print("🚀 Starting AIDA Bridge with fixed module paths...")
    
    # Set up environment with correct PYTHONPATH for src-layout
    env = os.environ.copy()
    project_root = str(Path.cwd())
    env.setdefault("PYTHONPATH", project_root)
    
    # Multiple startup methods to try (in order of preference)
    startup_methods = [
        {
            "name": "Module import (corrected path)",
            "cmd": [sys.executable, "-m", "src.aidamatic.bridge.app"],
            "description": "Uses correct module path with PYTHONPATH set"
        },
        {
            "name": "Direct FastAPI import",
            "cmd": [sys.executable, "-c", "from src.aidamatic.bridge.app import run; run()"],
            "description": "Direct import and run with correct module path"
        },
        {
            "name": "Direct script execution",
            "cmd": [sys.executable, "src/aidamatic/bridge/app.py"],
            "description": "Runs the app.py file directly"
        }
    ]
    
    for i, method in enumerate(startup_methods, 1):
        print(f"  Attempt {i}: {method['name']}")
        print(f"    {method['description']}")
        print(f"    Command: {' '.join(method['cmd'])}")
        
        try:
            # Start the process
            proc = subprocess.Popen(
                method["cmd"], 
                env=env,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            print(f"    Process started with PID: {proc.pid}")
            
            # Give it a moment to start up
            time.sleep(3)
            
            # Check if process is still running
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                print(f"    ❌ Process exited immediately!")
                print(f"    stdout: {stdout}")
                print(f"    stderr: {stderr}")
                continue
            
            # Try to connect to the health endpoint
            try:
                response = requests.get("http://127.0.0.1:8787/health", timeout=5)
                if response.status_code == 200:
                    print(f"    ✅ Bridge server started successfully!")
                    print(f"    Health check: {response.status_code} - {response.json()}")
                    return proc
                else:
                    print(f"    ❌ Health check failed: {response.status_code}")
            except requests.exceptions.ConnectionError:
                print("    ❌ Connection refused - server not responding")
            except requests.exceptions.Timeout:
                print("    ❌ Timeout - server not responding")
            except Exception as e:
                print(f"    ❌ Health check error: {e}")
            
            # If we get here, health check failed - log output and try next method
            try:
                stdout, stderr = proc.communicate(timeout=2)
                if stdout:
                    print(f"    stdout: {stdout}")
                if stderr:
                    print(f"    stderr: {stderr}")
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                if stdout:
                    print(f"    stdout: {stdout}")
                if stderr:
                    print(f"    stderr: {stderr}")
            
        except Exception as e:
            print(f"    ❌ Failed to start: {e}")
    
    print("❌ All startup methods failed!")
    return None

def test_bridge_endpoints(bridge_proc):
    """Test the main bridge endpoints to verify functionality."""
    if not bridge_proc:
        return False
    
    print("\n🧪 Testing Bridge endpoints...")
    endpoints = [
        ("/health", "Health check"),
        ("/", "Root endpoint"),
        ("/sync/state", "Sync state")
    ]
    
    all_passed = True
    for endpoint, description in endpoints:
        try:
            response = requests.get(f"http://127.0.0.1:8787{endpoint}", timeout=5)
            print(f"  ✅ {description}: {response.status_code}")
            if len(response.text) > 0:
                preview = response.text[:100] + "..." if len(response.text) > 100 else response.text
                print(f"    Response: {preview}")
        except Exception as e:
            print(f"  ❌ {description}: Failed - {e}")
            all_passed = False
    
    return all_passed

def main():
    """Main execution function."""
    print("AIDA Bridge Fixed Startup")
    print("=" * 50)
    
    # Check if bridge is already running
    try:
        response = requests.get("http://127.0.0.1:8787/health", timeout=1)
        if response.status_code == 200:
            print("✅ Bridge is already running!")
            test_bridge_endpoints(None)
            return 0
    except:
        pass
    
    # Start the bridge
    bridge_proc = start_bridge_fixed()
    
    if bridge_proc:
        print("\n🎉 Bridge server started successfully!")
        
        # Test endpoints
        endpoints_ok = test_bridge_endpoints(bridge_proc)
        
        if endpoints_ok:
            print("\n✅ All endpoint tests passed!")
            print("\nBridge is running at: http://127.0.0.1:8787")
            print("Press Ctrl+C to stop the server...")
            
            try:
                # Keep running until user stops
                bridge_proc.wait()
            except KeyboardInterrupt:
                print("\n🛑 Stopping Bridge server...")
                bridge_proc.terminate()
                try:
                    bridge_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print("  Force killing process...")
                    bridge_proc.kill()
                    bridge_proc.wait()
                print("  Bridge server stopped.")
        else:
            print("\n⚠️ Some endpoint tests failed, but server is running")
            return 1
    else:
        print("\n❌ Failed to start Bridge server")
        print("\nDebugging suggestions:")
        print("1. Check if all dependencies are installed: uv pip install -e .")
        print("2. Verify you're in the project root directory")
        print("3. Check if port 8787 is already in use")
        print("4. Check .aida/bridge.log for detailed error messages")
        return 1
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())