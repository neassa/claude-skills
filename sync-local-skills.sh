#!/usr/bin/env bash
set -euo pipefail
SRC="/home/neassa/.copilot/skills"
DEST="/home/neassa/claude-skills"
mkdir -p "$DEST"
cp -a "$SRC"/. "$DEST"/
cd "$DEST"
git add -A
if git diff --cached --quiet; then
  echo "No local skill changes to sync."
  exit 0
fi
git commit -m "Sync skills $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push origin main
