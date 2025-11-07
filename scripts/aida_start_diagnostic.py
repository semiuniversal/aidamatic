#!/usr/bin/env python3
"""
Enhanced AIDA startup with detailed diagnostics to find where it hangs
"""

import subprocess
import time
import sys
import requests
from pathlib import Path


def log_progress(message):
    """Log with timestamp for better debugging"""
    print(f"[{time.strftime('%H:%M:%S')}] {message}")
    sys.stdout.flush()


def check_docker_containers():
    """Check Docker container status"""
    log_progress("🔍 Checking Docker containers...")

    try:
        result = subprocess.run(['docker', 'compose', '-f', 'docker/docker-compose.yml', 'ps', '--format', 'json'],
                             capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            log_progress("✅ Docker containers running")
            for line in result.stdout.split('\n'):
                if line.strip():
                    log_progress(f"  - {line}")
            return True
        else:
            log_progress("❌ Docker containers check failed")
            return False
    except Exception as e:
        log_progress(f"❌ Docker check error: {e}")
        return False


def test_api_endpoints():
    """Test various API endpoints to see what's working"""
    log_progress("🌐 Testing API endpoints...")

    base_url = "http://localhost:9000"
    endpoints = [
        ("", "Root"),
        ("/api/v1", "API v1"),
        ("/api/v1/users", "Users API"),
        ("/api/v1/projects", "Projects API"),
    ]

    for endpoint, name in endpoints:
        try:
            url = f"{base_url}{endpoint}"
            response = requests.get(url, timeout=5)
            log_progress(f"  ✅ {name}: {response.status_code}")
        except requests.exceptions.ConnectionError:
            log_progress(f"  ❌ {name}: Connection failed")
        except requests.exceptions.Timeout:
            log_progress(f"  ⏰ {name}: Timeout")
        except Exception as e:
            log_progress(f"  ⚠️  {name}: {e}")


def test_internal_services():
    """Test internal Docker service communication"""
    log_progress("🏠 Testing internal service communication...")

    services = [
        ("taiga_back", "8000", "Backend API"),
        ("taiga_front", "80", "Frontend"),
        ("taiga_events", "8888", "Events"),
    ]

    for service, port, name in services:
        try:
            cmd = f"docker exec taiga_gateway curl -s -o /dev/null -w '%{{http_code}}' http://{service}:{port}/"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                log_progress(f"  ✅ {name}: HTTP {result.stdout.strip()}")
            else:
                log_progress(f"  ❌ {name}: Failed")
        except Exception as e:
            log_progress(f"  ❌ {name}: Error - {e}")


def check_bridge_server():
    """Check if Bridge server is accessible"""
    log_progress("🌉 Checking Bridge server...")

    try:
        response = requests.get("http://localhost:8787/health", timeout=5)
        log_progress(f"  ✅ Bridge health: {response.status_code}")
    except requests.exceptions.ConnectionError:
        log_progress("  ❌ Bridge: Not accessible")
    except requests.exceptions.Timeout:
        log_progress("  ❌ Bridge: Timeout")
    except Exception as e:
        log_progress(f"  ❌ Bridge: {e}")


def wait_for_bridge_with_diagnostics():
    """Wait for Bridge server with detailed diagnostics"""
    log_progress("⏳ Waiting for Bridge server...")

    max_attempts = 60  # 5 minutes max
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get("http://localhost:8787/health", timeout=5)
            if response.status_code == 200:
                log_progress(f"  ✅ Bridge ready after {attempt} attempts")
                return True
            else:
                log_progress(f"  ⏰ Attempt {attempt}: Bridge returned {response.status_code}")
        except requests.exceptions.ConnectionError:
            log_progress(f"  ⏰ Attempt {attempt}: Bridge not yet accessible")
        except requests.exceptions.Timeout:
            log_progress(f"  ⏰ Attempt {attempt}: Bridge timeout")
        except Exception as e:
            log_progress(f"  ⏰ Attempt {attempt}: Bridge error - {e}")

        time.sleep(5)

    log_progress("  ❌ Bridge never became ready")
    return False


def check_logs_recent():
    """Check recent logs for errors"""
    log_progress("📋 Checking recent container logs...")

    containers = ['taiga_gateway', 'taiga_back', 'taiga_front']
    for container in containers:
        try:
            log_progress(f"  Container: {container}")
            result = subprocess.run(['docker', 'logs', '--tail', '10', container],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines[-5:]:  # Show last 5 lines
                    if line.strip():
                        log_progress(f"    {line}")
        except Exception as e:
            log_progress(f"    Error getting logs: {e}")


def main():
    """Main diagnostic startup"""
    log_progress("🚀 Starting AIDA with enhanced diagnostics")
    log_progress("=" * 50)

    # Phase 1: Basic checks
    log_progress("PHASE 1: Container Status")
    check_docker_containers()

    log_progress("\nPHASE 2: API Testing")
    test_api_endpoints()

    log_progress("\nPHASE 3: Internal Services")
    test_internal_services()

    log_progress("\nPHASE 4: Bridge Server Check")
    check_bridge_server()

    log_progress("\nPHASE 5: Bridge Server Wait (with timeout)")
    bridge_ready = wait_for_bridge_with_diagnostics()

    if bridge_ready:
        log_progress("\n✅ SUCCESS: AIDA is fully operational!")
        log_progress("Bridge server is responding at http://localhost:8787")
    else:
        log_progress("\n❌ FAILED: Bridge server never became ready")
        log_progress("\nPHASE 6: Error Investigation")
        check_logs_recent()

    log_progress("\n" + "=" * 50)
    log_progress("Diagnostic complete")


if __name__ == "__main__":
    main()
