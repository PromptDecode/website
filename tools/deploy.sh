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

# `wrangler deploy`, not `wrangler pages deploy`: Cloudflare Pages is now served
# by Workers and the pages subcommands no longer work against a project current
# wrangler created. wrangler.jsonc in the worktree names the Worker and points
# at dist/, so this uploads the allowlist and nothing else.
#
# Do not run `wrangler pages project create` to set this up. It does not only
# create a project, it deploys the current working directory, and it scaffolds
# a wrangler.jsonc with `"directory": "."` that republishes the whole checkout
# on every later deploy.
(cd "$tmp/tree" && npx --yes wrangler@4 deploy --message "$subject")

# What is live must be the allowlist and nothing else. A deploy that uploads
# the repository instead of dist/ looks entirely successful, so the only way to
# know is to ask the origin for something that should not exist.
echo
echo "checking that no repository file is served:"

# Find an origin that actually answers. The first version of this check fell
# back to a hostname that did not exist, got a connection error for every path,
# counted each one as "not 200" and reported the site clean. A verification that
# passes when it cannot reach anything is worse than no verification, so an
# unreachable origin is a failure here, and so is any code other than 404.
base=""
for candidate in "https://promptdeco.de" "https://promptdecode.earthos-waitlist.workers.dev"; do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$candidate/" || true)" = "200" ]; then
    base="$candidate"
    break
  fi
  echo "  (no answer from $candidate)"
done
if [ -z "$base" ]; then
  echo "could not reach any origin to verify the deploy; check by hand before leaving this live" >&2
  exit 1
fi
echo "  origin $base"

bad=0
for path in /tools/check.py /tools/deploy.sh /COPY.md /README.md /LICENSE /.git/config /wrangler.jsonc; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$base$path" || echo 000)
  case "$code" in
    404) echo "  ok   $path -> 404" ;;
    200) echo "  LEAK $path is public ($base$path)"; bad=$((bad + 1)) ;;
    *)   echo "  ??   $path -> $code (expected 404)"; bad=$((bad + 1)) ;;
  esac
done
if [ "$bad" -gt 0 ]; then
  echo "$bad path(s) did not 404. Redeploy dist/, do not leave this live." >&2
  exit 1
fi
echo "clean: $base serves the allowlist only"
