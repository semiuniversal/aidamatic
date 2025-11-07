#!/bin/bash

echo "=== Deep AIDA Bridge Diagnosis ==="
echo

echo "1. Container Status Check:"
echo "=========================="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo

echo "2. Check if taiga-back is actually listening on port 8000:"
echo "========================================================="
docker exec taiga_back netstat -tlnp | grep :8000 || echo "❌ No process listening on port 8000"
echo

echo "3. Check taiga-back container logs for errors:"
echo "=============================================="
echo "Last 15 lines of taiga_back logs:"
docker logs --tail 15 taiga_back
echo

echo "4. Test internal connectivity from gateway to backend:"
echo "======================================================"
docker exec taiga_gateway wget -q -O - --timeout=10 --tries=2 http://taiga-back:8000/api/v1 || echo "❌ Cannot reach taiga-back:8000/api/v1 from gateway"
echo

echo "5. Check backend health status:"
echo "==============================="
docker inspect taiga_back --format='{{.State.Health.Status}}' 2>/dev/null || echo "No health check configured"
echo

echo "6. Test backend directly (bypassing nginx):"
echo "=========================================="
docker exec taiga_back wget -q -O - --timeout=5 http://127.0.0.1:8000/api/v1 || echo "❌ Cannot reach localhost:8000/api/v1 from within backend"
echo

echo "7. Check nginx configuration loading:"
echo "===================================="
docker exec taiga_gateway nginx -T 2>/dev/null | grep -A 10 "location /api/" || echo "❌ No /api/ location found in nginx config"
echo

echo "=== Diagnosis Complete ==="