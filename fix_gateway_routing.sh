#!/bin/bash

echo "=== AIDA Bridge Gateway Routing Fix ==="
echo

echo "Current directory: $(pwd)"
echo "Files in current directory:"
ls -la
echo

# Check if we're in the right directory - try different possible filenames
DOCKER_COMPOSE_FILE=""
if [ -f "docker-compose.yml" ]; then
    DOCKER_COMPOSE_FILE="docker-compose.yml"
    echo "✅ Found: docker-compose.yml"
elif [ -f "docker-compose.yaml" ]; then
    DOCKER_COMPOSE_FILE="docker-compose.yaml"
    echo "✅ Found: docker-compose.yaml"
elif [ -f "docker-composer.yml" ]; then
    DOCKER_COMPOSE_FILE="docker-composer.yml"
    echo "✅ Found: docker-composer.yml"
else
    echo "❌ ERROR: No docker-compose file found!"
    echo
    echo "Please run this script from the AIDA Bridge project root directory"
    echo "Expected to find one of: docker-compose.yml, docker-compose.yaml, or docker-composer.yml"
    echo
    echo "Please copy this script to your project directory that contains the docker-compose file."
    exit 1
fi

echo

echo "1. Checking if taiga_gateway container exists..."
if ! docker ps -a --format '{{.Names}}' | grep -q "^taiga_gateway$"; then
    echo "❌ ERROR: taiga_gateway container not found!"
    echo "Available containers:"
    docker ps -a --format '{{.Names}}'
    exit 1
fi
echo "✅ taiga_gateway container found"

echo
echo "2. Restarting nginx gateway container..."
docker restart taiga_gateway

echo
echo "3. Waiting 5 seconds for gateway to fully restart..."
sleep 5

echo
echo "4. Testing /api/v1 endpoint..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/api/v1)

echo "HTTP Response Code: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ SUCCESS: /api/v1 is now responding with 200 OK!"
    echo
    echo "You can now run: ./setup.sh --bootstrap"
    echo "The gateway check should now pass."
else
    echo "❌ STILL FAILING: /api/v1 returns $HTTP_CODE"
    echo
    echo "Additional debugging needed. Let's check the services:"
    echo
    echo "Container status:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    echo
    echo "Gateway logs (last 10 lines):"
    docker logs --tail 10 taiga_gateway
    echo
    echo "Backend logs (last 5 lines):"
    docker logs --tail 5 taiga_back
    echo
    echo "5. If the issue persists, try running the deep diagnostic script:"
    echo "   ./deep_nginx_diagnostic.sh"
fi

echo
echo "=== End of Gateway Routing Fix ==="