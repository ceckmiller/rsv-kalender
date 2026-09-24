#!/usr/bin/env bash
# Netlify: exit 0 = skip build, exit 1 = run build.
# Calendar runs publish live data to Netlify Blobs and must not spend a deploy.
set -euo pipefail

msg="${COMMIT_REF_MESSAGE:-}"
if [[ -z "$msg" ]]; then
  msg="$(git log -1 --pretty=%B 2>/dev/null || true)"
fi

if [[ "$msg" == *"[skip netlify]"* || "$msg" == *"[skip ci]"* ]]; then
  echo "Build übersprungen: Commit-Nachricht enthält skip-Marker."
  exit 0
fi

# Fallback: a calendar commit only touches docs/ and data/.
if [[ -n "${CACHED_COMMIT_REF:-}" && -n "${COMMIT_REF:-}" ]]; then
  if ! git cat-file -e "${CACHED_COMMIT_REF}^{commit}" 2>/dev/null; then
    git fetch --depth=1 origin "${CACHED_COMMIT_REF}" 2>/dev/null || true
  fi
  if git cat-file -e "${CACHED_COMMIT_REF}^{commit}" 2>/dev/null; then
    only_calendar=1
    found=0
    while IFS= read -r file; do
      [[ -z "$file" ]] && continue
      found=1
      case "$file" in
        docs/*|data/*) ;;
        *) only_calendar=0 ;;
      esac
    done < <(git diff --name-only "${CACHED_COMMIT_REF}" "${COMMIT_REF}")
    if [[ "$found" -eq 1 && "$only_calendar" -eq 1 ]]; then
      echo "Build übersprungen: nur Kalenderdaten (docs/, data/) geändert. Live-Stand kommt aus Netlify Blobs."
      exit 0
    fi
  fi
fi

echo "Build nötig: Code oder Konfiguration hat sich geändert."
exit 1
