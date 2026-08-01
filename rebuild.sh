#!/bin/bash
echo "=== Rebuilding Nami Docker Container ==="
docker compose build --no-cache
docker compose up -d
echo "=== Nami successfully rebuilt and running! ==="
