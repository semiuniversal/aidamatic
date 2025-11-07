#!/bin/bash

echo "=== AIDA Bridge Host-Side Diagnostic ==="
echo

echo "1. Host-Side Port Monitoring:"
echo "============================="
echo "Checking what's listening on port 8000 from HOST machine..."
netstat -tlnp 2>/dev/null | grep :8000 || echo "❌ Nothing listening on port 8000 from host"
echo
echo "Checking what's listening on port 9000 from HOST machine..."
netstat -tlnp 2>/dev/null | grep :9000 || echo "❌ Nothing listening on port 9000 from host"
echo

echo "2. Docker Container Port Mapping:"
echo "================================="
echo "All taiga containers and their port mappings:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(taiga|8000|9000)"
echo

echo "3. Test Backend Connectivity from Host:"
echo "======================================="
echo "Direct connection test to backend port 8000..."
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/localhost/8000' 2>/dev/null && echo "✅ Can connect to port 8000 from host" || echo "❌ Cannot connect to port 8000 from host"
echo

echo "4. Test Nginx Gateway from Host:"
echo "================================"
echo "Testing nginx on port 9000..."
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/localhost/9000' 2>/dev/null && echo "✅ Can connect to port 9000 from host" || echo "❌ Cannot connect to port 9000 from host"
echo

echo "5. Backend Container Process Check (using Docker):"
echo "================================================="
echo "Backend container process info:"
docker exec taiga_back sh -c 'cat /proc/1/cmdline | tr "\0" " " && echo'
echo
echo "All processes in backend container:"
docker exec taiga_back sh -c 'ls -la /proc/[0-9]*/cmdline 2>/dev/null | head -10'
echo

echo "6. Container Network Inspection:"
echo "==============================="
echo "Inspecting backend container network settings..."
docker inspect taiga_back --format='{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' 
echo
echo "Inspecting gateway container network settings..."
docker inspect taiga_gateway --format='{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}'
echo

echo "7. Test Internal Docker Network:"
echo "==============================="
echo "Testing connectivity from gateway to backend via Docker network..."
GATEWAY_IP=$(docker inspect taiga_gateway --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
BACKEND_IP=$(docker inspect taiga_back --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
echo "Gateway IP: $GATEWAY_IP"
echo "Backend IP: $BACKEND_IP"
if [ -n "$BACKEND_IP" ]; then
    timeout 3 bash -c "cat < /dev/null > /dev/tcp/$BACKEND_IP/8000" 2>/dev/null && echo "✅ Can reach backend from gateway container" || echo "❌ Cannot reach backend from gateway container"
else
    echo "❌ Could not determine backend IP"
fi
echo

echo "8. Final HTTP Test:"
echo "==================="
echo "Testing /api/v1 endpoint via HTTP..."
curl -s -o /dev/null -w "HTTP Code: %{http_code}\n" http://localhost:9000/api/v1
echo

echo "=== Host-Side Diagnostic Complete ==="