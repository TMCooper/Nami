#!/bin/bash
echo "=== Rebuilding Nami Docker Container ==="
sudo docker compose build --no-cache
sudo docker compose up -d
sudo docker system prune -a
echo "=== Nami successfully rebuilt and running! ==="
