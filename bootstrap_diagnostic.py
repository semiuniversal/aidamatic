#!/usr/bin/env python3
"""
Quick diagnostic script to check Docker container status and identify bootstrap issues
"""
import subprocess
import sys
import time
import requests
from pathlib import Path

def check_docker_status():
    """Check if Docker is running and containers are up"""
    print("🐳 Checking Docker Status")
    print("=" * 40)
    
    # Check if Docker is running
    try:
        result = subprocess.run(["docker", "ps"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print("❌ Docker is not running or accessible")
            print(f"Error: {result.stderr}")
            return False
        else:
            print("✅ Docker is running")
            print("Current containers:")
            print(result.stdout)
            return True
    except Exception as e:
        print(f"❌ Failed to check Docker status: {e}")
        return False

def check_docker_compose_services():
    """Check if docker-compose services are running"""
    print("\n📦 Checking Docker Compose Services")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not Path("docker/docker-compose.yml").exists():
        print("❌ docker/docker-compose.yml not found. Are you in the project root?")
        return False
    
    # Check compose services status
    try:
        result = subprocess.run(["docker", "compose", "ps"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print("❌ Docker Compose command failed")
            print(f"Error: {result.stderr}")
            return False
        else:
            print("✅ Docker Compose services status:")
            print(result.stdout)
            return True
    except Exception as e:
        print(f"❌ Failed to check Compose services: {e}")
        return False

def check_gateway_health():
    """Check if the gateway at localhost:9000 is responding"""
    print("\n🌐 Checking Gateway Health (localhost:9000)")
    print("=" * 40)
    
    gateway_urls = [
        "http://localhost:9000/",
        "http://localhost:9000/api/v1",
        "http://localhost:9000/api/v1/auth"
    ]
    
    for url in gateway_urls:
        try:
            print(f"Testing: {url}")
            response = requests.get(url, timeout=5)
            print(f"  ✅ Status: {response.status_code}")
            if response.status_code == 200:
                print(f"  Response preview: {response.text[:200]}...")
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Connection refused - service not running")
        except requests.exceptions.Timeout:
            print(f"  ⏰ Timeout - service not responding")
        except Exception as e:
            print(f"  ❌ Error: {e}")
        print()

def check_bridge_health():
    """Check if the bridge at localhost:8787 is responding"""
    print("🌉 Checking Bridge Health (localhost:8787)")
    print("=" * 40)
    
    try:
        response = requests.get("http://localhost:8787/health", timeout=5)
        if response.status_code == 200:
            print("✅ Bridge is running and responding")
            print(f"Response: {response.json()}")
        else:
            print(f"⚠️ Bridge responding but health check failed: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Bridge not running")
    except requests.exceptions.Timeout:
        print("⏰ Bridge timeout")
    except Exception as e:
        print(f"❌ Bridge error: {e}")

def check_logs():
    """Check recent Docker logs for errors"""
    print("\n📋 Checking Docker Logs")
    print("=" * 40)
    
    services = ["taiga-back", "gateway", "taiga-front", "postgres", "rabbit", "redis"]
    
    for service in services:
        try:
            print(f"\n--- Last 10 lines from {service} ---")
            result = subprocess.run(
                ["docker", "compose", "logs", "--tail", "10", service], 
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                print(result.stdout)
            else:
                print("No logs or error getting logs")
        except Exception as e:
            print(f"Error getting logs for {service}: {e}")

def check_port_conflicts():
    """Check if required ports are in use"""
    print("\n🔌 Checking Port Usage")
    print("=" * 40)
    
    ports = [9000, 8787, 5432, 5672, 6379]  # Gateway, Bridge, Postgres, RabbitMQ, Redis
    
    for port in ports:
        try:
            result = subprocess.run(
                ["lsof", "-i", f":{port}"], 
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                print(f"Port {port}: ✅ In use")
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:  # More than just header
                    for line in lines[:3]:  # Show first 3 processes
                        print(f"  {line}")
            else:
                print(f"Port {port}: ❌ Available")
        except FileNotFoundError:
            print(f"Port {port}: lsof not available (can't check)")
        except Exception as e:
            print(f"Port {port}: Error checking - {e}")

def main():
    print("AIDA Bootstrap Diagnostic Tool")
    print("=" * 50)
    print("This script will help identify why your bootstrap is hanging.\n")
    
    # Run all checks
    docker_ok = check_docker_status()
    if not docker_ok:
        print("\n❌ Docker is not running! This is likely the cause of your hanging.")
        print("Please:")
        print("1. Make sure Docker Desktop is running")
        print("2. Enable WSL2 integration if on Windows")
        print("3. Try running: docker ps")
        return 1
    
    compose_ok = check_docker_compose_services()
    check_logs()
    check_port_conflicts()
    check_gateway_health()
    check_bridge_health()
    
    print("\n" + "=" * 50)
    print("DIAGNOSTIC SUMMARY:")
    if compose_ok:
        print("✅ Docker and Compose are working")
        print("🔍 Check the logs above to see why containers aren't starting")
        print("💡 Try: docker compose up -d")
        print("💡 Then: docker compose logs gateway")
    else:
        print("❌ Docker Compose issues detected")
        print("🔧 Try: docker compose config")
        print("🔧 Check docker/.env file exists")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())