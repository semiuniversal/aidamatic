#!/bin/bash

echo "=== AIDA Bridge Backend Fix ==="
echo

echo "1. Checking backend process status:"
echo "=================================="
docker exec taiga_back ps aux
echo

echo "2. Testing backend port binding more thoroughly:"
echo "==============================================="
docker exec taiga_back sh -c 'netstat -tlnp || echo "netstat not available"'
docker exec taiga_back sh -c 'ss -tlnp || echo "ss not available"'
echo

echo "3. Restarting taiga-back container to fix port binding:"
echo "======================================================"
docker restart taiga_back
echo "✅ Backend restarted, waiting 30 seconds for full startup..."
sleep 30
echo

echo "4. Testing port binding after restart:"
echo "======================================"
docker exec taiga_back sh -c 'netstat -tlnp | grep :8000 || echo "Still not listening on port 8000"'
echo

echo "5. Testing /api/v1 after backend restart:"
echo "========================================="
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/api/v1)
echo "HTTP Response Code: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    echo "🎉 SUCCESS! Backend is now working!"
    echo
    echo "You can run: ./setup.sh --bootstrap"
else
    echo "❌ Backend restart didn't fix the issue."
    echo
    echo "Let's check the backend logs for any errors:"
    docker logs --tail 20 taiga_back
    echo
    echo "The backend may need a full restart of all services."
    echo "Try the full service restart: ./fix_service_restart.sh"
fi

echo
echo "=== Backend Fix Complete ==="