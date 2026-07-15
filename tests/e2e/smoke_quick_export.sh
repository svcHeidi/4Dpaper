#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_TAG="${IMAGE_TAG:-4dpapers-quick-smoke}"
HOST_PORT="${HOST_PORT:-5013}"
CONTAINER_NAME="4dpapers-quick-${HOST_PORT}"
QUICK_SOURCE="$(mktemp -d "${TMPDIR:-/tmp}/4dpapers-quick-source.XXXXXX")"
QUICK_OUTPUT="$(mktemp -d "${TMPDIR:-/tmp}/4dpapers-quick-output.XXXXXX")"
LAUNCHER_PID=""

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

cleanup() {
  if [[ -n "$LAUNCHER_PID" ]]; then
    kill -TERM "$LAUNCHER_PID" >/dev/null 2>&1 || true
    wait "$LAUNCHER_PID" 2>/dev/null || true
  fi
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  rm -rf "$QUICK_SOURCE" "$QUICK_OUTPUT"
}
trap cleanup EXIT

cd "$ROOT_DIR"
cp tests/data/test_data.vtu "$QUICK_SOURCE/test_data.vtu"
SOURCE_HASH_BEFORE="$(hash_file "$QUICK_SOURCE/test_data.vtu")"

echo "[quick-smoke] Starting isolated Quick Export with ${IMAGE_TAG}"
IMAGE="$IMAGE_TAG" ./development/quick-export/4d-quick.sh \
  "$QUICK_SOURCE/test_data.vtu" \
  --output-dir "$QUICK_OUTPUT" \
  --port "$HOST_PORT" \
  --no-browser > /tmp/4dpapers-quick-smoke.log 2>&1 &
LAUNCHER_PID=$!

ready=0
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${HOST_PORT}/api/quick-target" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  cat /tmp/4dpapers-quick-smoke.log
  exit 1
fi

echo "[quick-smoke] Rendering figure HTML"
curl -fsS -X POST "http://127.0.0.1:${HOST_PORT}/api/quick-init" \
  > /tmp/4dpapers-quick-init.json
grep '"status": "ok"' /tmp/4dpapers-quick-init.json >/dev/null

echo "[quick-smoke] Rendering standalone HTML"
curl -fsS -X POST "http://127.0.0.1:${HOST_PORT}/api/quick-export" \
  -H 'Content-Type: application/json' \
  --data '{"fig_id":"fig-test_data"}' \
  -o /tmp/4dpapers-quick-standalone.html

test -s "$QUICK_OUTPUT/fig-test_data.html"
test -s "$QUICK_OUTPUT/fig-test_data-standalone.html"
test "$(find "$QUICK_OUTPUT" -maxdepth 1 -type f | wc -l | tr -d ' ')" = 2
! grep -q '/state/figures/' /tmp/4dpapers-quick-standalone.html
test "$SOURCE_HASH_BEFORE" = "$(hash_file "$QUICK_SOURCE/test_data.vtu")"

MOUNTS="$(docker inspect "$CONTAINER_NAME" --format '{{range .Mounts}}{{println .Destination .RW .Source}}{{end}}')"
grep '^/workspace/source false ' <<<"$MOUNTS" >/dev/null
grep '^/quick-output true ' <<<"$MOUNTS" >/dev/null
RUNTIME_WORKSPACE="$(awk '$1 == "/workspace" {print $3}' <<<"$MOUNTS")"

kill -TERM "$LAUNCHER_PID"
wait "$LAUNCHER_PID" 2>/dev/null || true
LAUNCHER_PID=""
test ! -e "$RUNTIME_WORKSPACE"
! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1

echo "[quick-smoke] Isolated Quick Export smoke test passed"
