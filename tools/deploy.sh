#!/usr/bin/env bash
# Deploys promptdeco.de from origin/main, and from nothing else.
#
#     tools/deploy.sh             build origin/main in a throwaway worktree, deploy it
#     tools/deploy.sh --dry-run   build it and say what would ship, deploy nothing
#
# Why not `build-dist.sh && wrangler pages deploy dist` from wherever you are:
# that ships the contents of a working copy, and a working copy is shared state.
# More than one agent can work in the same checkout at once. Deploying from it
# can publish another session's uncommitted edits, or a checkout that is behind
# main and quietly rolls back work that was merged minutes ago.
#
# So this never reads the caller's working tree or its dist/. It fetches,
# checks origin/main out into a temporary worktree, checks and builds there,
# deploys that, and removes it. What goes live is always a commit that is on
# main, and the Pages deployment records which one.
#
# Cloudflare credentials: the Factory0 account, via CLOUDFLARE_API_TOKEN or
# `wrangler login` (see README, Deploy).
set -euo pipefail

dry_run=0
case "${1:-}" in
  "") ;;
  --dry-run) dry_run=1 ;;
  *) echo "usage: tools/deploy.sh [--dry-run]" >&2; exit 2 ;;
esac

root=$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)
cd "$root"

git fetch --quiet origin main
sha=$(git rev-parse origin/main)
subject=$(git log -1 --format=%s "$sha")

tmp=$(mktemp -d "${TMPDIR:-/tmp}/promptdecode-deploy.XXXXXX")
cleanup() {
  git -C "$root" worktree remove --force "$tmp/tree" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

git worktree add --quiet --detach "$tmp/tree" "$sha"
python3 "$tmp/tree/tools/check.py" "$tmp/tree"
"$tmp/tree/tools/build-dist.sh" >/dev/null

files=$(find "$tmp/tree/dist" -type f | wc -l | tr -d ' ')
echo "origin/main ${sha:0:7}  $subject"
echo "built $files files in a clean checkout"

if [ "$dry_run" = 1 ]; then
  echo "dry run: nothing deployed"
  exit 0
fi

npx --yes wrangler@4 pages deploy "$tmp/tree/dist" \
  --project-name=promptdecode \
  --branch=main \
  --commit-hash="$sha" \
  --commit-message="$subject" \
  --commit-dirty=false
