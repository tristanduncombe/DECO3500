#!/usr/bin/env bash
set -euo pipefail

# Run the DECO3500 stack on Raspberry Pi using Podman with GPIO enabled.
# Requires: podman and either 'podman compose' or podman-compose.

# Prefer 'podman compose' if available
if podman compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(podman compose)
elif command -v podman-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(podman-compose)
else
  echo "Error: neither 'podman compose' nor 'podman-compose' is available." >&2
  exit 1
fi

command -v podman >/dev/null 2>&1 || { echo "Error: podman not found" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -e /dev/gpiomem ] && [ ! -e /dev/gpiochip0 ]; then
  echo "Warning: no GPIO devices (/dev/gpiomem or /dev/gpiochip0) present; GPIO will not be available inside the container." >&2
fi

set -x
"${COMPOSE_CMD[@]}" -f docker-compose.yml -f docker-compose.gpio.yml up --build -d
set +x

echo "Stack is starting. UI: http://localhost:3000, API: http://localhost:8000"
