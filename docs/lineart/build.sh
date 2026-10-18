#!/usr/bin/env bash
# Bluespeaker Mini: the line-art images and the spec sheet PDF.
# Run from anywhere. Needs Node.js, Chromium, and ImageMagick 7. Takes about 20 s.
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -d docs/lineart/node_modules ] || (cd docs/lineart && npm ci --no-fund --no-audit)
node docs/lineart/render.mjs > /dev/null
mkdir -p docs/lineart/img
for f in docs/lineart/raw/*.png; do
  magick "$f" -trim +repage -bordercolor none -border 24 "docs/lineart/img/$(basename "$f")"
done
chromium --headless --no-sandbox --no-pdf-header-footer --virtual-time-budget=15000 \
  --print-to-pdf=docs/Bluespeaker-Mini-Specs.pdf "file://$PWD/docs/specs-mini/index.html" 2> /dev/null
echo "wrote docs/lineart/img/ and docs/Bluespeaker-Mini-Specs.pdf"
