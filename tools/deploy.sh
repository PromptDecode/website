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

# Create the project on first run, from INSIDE dist/.
#
# `wrangler pages project create` does not just create a project: on the
# Workers-backed Pages it also deploys the current working directory. Run from
# the repository root it published all 92 files of the checkout, tools/,
# COPY.md and .git/config included, which is the exact leak build-dist.sh's
# allowlist exists to prevent. Running it from dist/ means the worst it can
# upload is the set of files that were going to ship anyway.
if ! npx --yes wrangler@4 pages project list 2>/dev/null | grep -q '\bpromptdecode\b'; then
  echo "creating the Pages project (first deploy)"
  (cd "$tmp/tree/dist" && npx --yes wrangler@4 pages project create promptdecode --production-branch=main)
fi

npx --yes wrangler@4 pages deploy "$tmp/tree/dist" \
  --project-name=promptdecode \
  --branch=main \
  --commit-hash="$sha" \
  --commit-message="$subject" \
  --commit-dirty=false

# What is live must be the allowlist and nothing else. A deploy that uploads
# the repository instead of dist/ looks entirely successful, so the only way to
# know is to ask the origin for something that should not exist.
echo
echo "checking that no repository file is served:"
base="https://promptdeco.de"
curl -sf -o /dev/null --max-time 10 "$base/" 2>/dev/null || base="https://promptdecode.pages.dev"
leaked=0
for path in /tools/check.py /tools/deploy.sh /COPY.md /README.md /LICENSE /.git/config; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$base$path" || echo 000)
  case "$code" in
    200) echo "  LEAK $path is public ($base$path)"; leaked=$((leaked + 1)) ;;
    *)   echo "  ok   $path -> $code" ;;
  esac
done
if [ "$leaked" -gt 0 ]; then
  echo "$leaked repository file(s) are being served. Redeploy dist/, do not leave this live." >&2
  exit 1
fi
echo "clean: $base serves the allowlist only"
