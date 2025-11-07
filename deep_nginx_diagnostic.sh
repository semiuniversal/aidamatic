#!/bin/bash

echo "=== Deep Nginx Routing Diagnostic ==="
echo

# Test 1: Check if backend is reachable internally
echo "1. Testing internal backend connectivity:"
echo "========================================="
docker exec taiga_gateway wget -q -O - http://taiga-back:8000/api/v1 | head -1
INTERNAL_CODE=$?
if [ $INTERNAL_CODE -eq 0 ]; then
    echo "✅ Backend is reachable internally"
else
    echo "❌ Backend is NOT reachable internally (exit code: $INTERNAL_CODE)"
fi
echo

# Test 2: Check backend logs for any startup issues
echo "2. Backend container health check:"
echo "=================================="
docker inspect taiga_back --format='{{.State.Health.Status}}' 2>/dev/null || echo "No health check configured"
echo

# Test 3: Check if backend is actually listening on port 8000
echo "3. Backend port check:"
echo "====================="
docker exec taiga_back netstat -tlnp | grep :8000 || echo "No process listening on port 8000"
echo

# Test 4: Check nginx config syntax
echo "4. Nginx config validation:"
echo "==========================="
docker exec taiga_gateway nginx -t
if [ $? -eq 0 ]; then
    echo "✅ Nginx config is syntactically correct"
else
    echo "❌ Nginx config has syntax errors"
fi
echo

# Test 5: Full nginx configuration dump
echo "5. Loaded nginx configuration:"
echo "=============================="
docker exec taiga_gateway nginx -T 2>/dev/null | grep -A 20 "location /api/" || echo "API location not found in config"
echo

echo "=== Deep Diagnostic Complete ==="