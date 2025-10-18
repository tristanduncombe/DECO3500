#!/usr/bin/env bash
set -euo pipefail

# Run the DECO3500 stack on Raspberry Pi using Podman with GPIO enabled.
# Requires: podman and either podman-compose or 'podman compose' subcommand.

# Detect compose command
if command -v podman-compose >/dev/null 2>&1; then
  COMPOSE_CMD="podman-compose"
elif podman compose version >/dev/null 2>&1; then
  COMPOSE_CMD="podman compose"
else
  echo "Error: podman-compose not found and 'podman compose' unavailable. Install podman-compose or upgrade Podman." >&2
  exit 1
fi

# Ensure podman exists
command -v podman >/dev/null 2>&1 || { echo "Error: podman not found" >&2; exit 1; }

# Move to repo root (this script's directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Warn if GPIO device is missing
if [ ! -e /dev/gpiomem ]; then
  echo "Warning: /dev/gpiomem not present; GPIO will not be available inside the container." >&2
fi

# Build and start with GPIO override
set -x
$COMPOSE_CMD -f docker-compose.yml -f docker-compose.gpio.yml up --build -d
set +x

echo "Stack is starting. UI: http://localhost:3000, API: http://localhost:8000"
