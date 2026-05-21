#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

git pull
docker compose down
docker compose up -d --build
docker compose logs -f --tail=100

