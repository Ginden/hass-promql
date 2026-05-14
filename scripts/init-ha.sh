#!/bin/sh
# Copy the seed config into the HA config dir on first run.
# Runs as an init container before HA starts.
set -e

TARGET=/ha-config
SEED=/ha-seed
MARKER="$TARGET/.storage/onboarding"

if [ -f "$MARKER" ]; then
  echo "HA already initialized — skipping seed."
  exit 0
fi

echo "First run: seeding HA config from $SEED..."
mkdir -p "$TARGET/.storage"
cp -r "$SEED/." "$TARGET/"
echo "Done."
echo ""
echo "  URL:      http://localhost:8123"
echo "  Username: dev"
echo "  Password: dev"
