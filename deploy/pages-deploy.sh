#!/usr/bin/env bash
#
# pages-deploy.sh — publish the verified Niederer live demo to GitHub Pages.
#
# The demo (examples/niederer/_output/main-standalone.html + main_files/) is a
# self-contained WebGL page, but it lives under gitignored _output/, so it is
# force-copied onto an orphan `gh-pages` branch rather than committed to main.
#
# Prereqs:
#   - Run from the repo root, on a clean working tree.
#   - examples/niederer/_output/main-standalone.html must exist (rebuild the
#     Niederer example if it does not).
#   - A remote named `origin` you can push to.
#
# After running: GitHub -> repo Settings -> Pages -> Source: `gh-pages` branch, / root.
#
set -euo pipefail

SRC_HTML="examples/niederer/_output/main-standalone.html"
SRC_LIBS="examples/niederer/_output/main_files"
STAGE="$(mktemp -d)"

if [[ ! -f "$SRC_HTML" ]]; then
  echo "ERROR: $SRC_HTML not found. Rebuild the Niederer example first." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree is dirty. Commit or stash first." >&2
  exit 1
fi

START_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

echo "Staging demo -> $STAGE"
cp "$SRC_HTML" "$STAGE/index.html"
cp -r "$SRC_LIBS" "$STAGE/main_files"
# .nojekyll stops GitHub Pages Jekyll from mangling the main_files/ directory.
touch "$STAGE/.nojekyll"

echo "Building orphan gh-pages branch"
git switch --orphan gh-pages
git rm -rf . >/dev/null 2>&1 || true
cp -r "$STAGE"/. .
git add -A
git commit -m "Deploy Niederer live demo to GitHub Pages"
git push -f -u origin gh-pages

git switch "$START_BRANCH"
rm -rf "$STAGE"

echo
echo "Done. Now enable Pages: Settings -> Pages -> Source: gh-pages / root."
echo "Then verify the published URL on desktop AND mobile before announcing."
