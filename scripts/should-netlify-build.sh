#!/usr/bin/env bash
# Netlify: exit 0 = skip build, exit 1 = run build.
set -euo pipefail

msg="${COMMIT_REF_MESSAGE:-}"
if [[ "$msg" == *"[skip netlify]"* ]] || [[ "$msg" == *"[skip ci]"* ]]; then
  echo "Build übersprungen: Commit-Nachricht enthält skip-Marker."
  exit 0
fi

# Always build: calendar results live in docs/*.json and docs/*.ics.
# Skipping those files left the site stuck whenever Netlify Blobs secrets
# were missing from GitHub Actions.
echo "Build nötig: Deploy liefert aktuelle Spieldaten und ICS-Dateien."
exit 1
