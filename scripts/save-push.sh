#!/usr/bin/env bash
# Save the current work and push it.
#
#   scripts/save-push.sh                        # message: "Save changes <date time>"
#   scripts/save-push.sh "Fix vaccination row"  # your own message
#
# Staging rules come from scripts/save.sh: every change is saved, editor history
# (.history/) and screenshots in the project root never are. If there is nothing
# new to save, commits that are still local are pushed anyway; if there is nothing
# to save and nothing to push, it exits 1.
set -uo pipefail

cd "$(dirname "$0")/.."

status=0
bash scripts/save.sh "${1:-}" || status=$?
case "$status" in
  0|1) ;;                                   # 0 = saved, 1 = nothing to save
  *) echo "Save failed (exit $status); nothing was pushed." >&2; exit "$status" ;;
esac

upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null) || {
  echo "No upstream branch set. Run: git push -u origin $(git rev-parse --abbrev-ref HEAD)" >&2
  exit 1
}

if [ "$(git rev-list --count "$upstream..HEAD")" -eq 0 ]; then
  echo "Nothing to push: already up to date with $upstream." >&2
  exit "$status"
fi

git push
