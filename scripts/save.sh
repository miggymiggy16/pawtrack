#!/usr/bin/env bash
# Save the current work as a local commit. Nothing is pushed.
#
#   scripts/save.sh                        # message: "Save changes <date time>"
#   scripts/save.sh "Fix vaccination row"  # your own message
#
# Stages every change (new files too). Editor history (.history/) and screenshots
# dropped in the project root are never included. Run `git push` when you want the
# commit on GitHub.
set -euo pipefail

cd "$(dirname "$0")/.."

msg=${1:-}
[ -n "$msg" ] || msg="Save changes $(date '+%Y-%m-%d %H:%M')"

git add -A
git reset -q -- .history ':(top)*.png' ':(top)*.jpg' ':(top)*.jpeg' ':(top)*.webp' 2>/dev/null || true

if git diff --cached --quiet; then
  echo "Nothing to save: no tracked changes." >&2
  exit 1
fi

git commit -m "$msg"
