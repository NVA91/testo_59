#!/bin/bash
# Ins Hauptverzeichnis springen
cd "$(dirname "$0")/../.."

# 1. Alte Container-Reste sauber entfernen
docker compose -f deploy/docker/docker-compose.yml down --remove-orphans

# 2. Neu bauen und starten
docker compose -f deploy/docker/docker-compose.yml up --build
