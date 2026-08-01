#!/usr/bin/env bash
# Netlify: exit 0 = skip build, exit 1 = run build.
set -euo pipefail

msg="${COMMIT_REF_MESSAGE:-}"
if [[ "$msg" == *"[skip netlify]"* ]] || [[ "$msg" == *"[skip ci]"* ]]; then
  echo "Build übersprungen: Commit-Nachricht enthält skip-Marker."
  exit 0
fi

if [[ -z "${CACHED_COMMIT_REF:-}" || -z "${COMMIT_REF:-}" ]]; then
  exit 1
fi

mapfile -t changed < <(git diff --name-only "$CACHED_COMMIT_REF" "$COMMIT_REF")
if ((${#changed[@]} == 0)); then
  exit 1
fi

for file in "${changed[@]}"; do
  case "$file" in
    docs/site-data.json|docs/rsv-*.ics|data/*.json) ;;
    *) echo "Build nötig: $file geändert."; exit 1 ;;
  esac
done

echo "Build übersprungen: nur Livedaten geändert (werden über Netlify Blobs ausgeliefert)."
exit 0
