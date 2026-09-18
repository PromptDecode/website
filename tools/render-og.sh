#!/usr/bin/env bash
# Regenerates assets/og.png, assets/readme-banner.png, assets/org-avatar.png and
# the app icons from tools/og-render.html, tools/banner-render.html,
# tools/avatar-render.html and assets/favicon.svg, using headless Chrome.
# The same shape as colonizer.dev's and supportgeni.us's tools/render-og.sh.
#
# assets/org-avatar.png is uploaded by hand: GitHub has no API for organisation
# avatars (github.com/organizations/PromptDecode/settings/profile).
# assets/readme-banner.png is also the org profile banner in PromptDecode/.github.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

shoot() { # src w h out [scale]
  "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --force-device-scale-factor="${5:-1}" --window-size="$2,$3" \
    --virtual-time-budget=10000 --screenshot="$4" "file://$1" >/dev/null 2>&1
}

shoot "$ROOT/tools/og-render.html" 1200 630 "$ROOT/assets/og.png"
shoot "$ROOT/tools/banner-render.html" 1280 400 "$ROOT/assets/readme-banner.png" 2
shoot "$ROOT/tools/avatar-render.html" 512 512 "$ROOT/assets/org-avatar.png"

# App icons: Chrome ignores window widths under ~500px, so render at 512 and downscale.
cat > "$TMP/icon.html" <<HTML
<!DOCTYPE html><meta charset="utf-8">
<style>html,body{margin:0;background:#000000;width:512px;height:512px}
svg{display:block;width:512px;height:512px}</style>
$(cat "$ROOT/assets/favicon.svg")
HTML
shoot "$TMP/icon.html" 512 512 "$TMP/icon512.png"
cp "$TMP/icon512.png" "$ROOT/assets/icon-512.png"
sips -z 180 180 "$TMP/icon512.png" --out "$ROOT/assets/apple-touch-icon.png" >/dev/null

for f in og.png readme-banner.png org-avatar.png apple-touch-icon.png icon-512.png; do
  printf '%-22s %-24s %s\n' "$f" "$(sips -g pixelWidth -g pixelHeight "$ROOT/assets/$f" | tail -2 | awk '{print $2}' | paste -sd x -)" "$(( $(stat -f%z "$ROOT/assets/$f") / 1024 )) KB"
done
