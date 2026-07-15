#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_TAG="${IMAGE_TAG:-4dpapers-deploy-smoke}"
CONTAINER_NAME="${CONTAINER_NAME:-4dpapers-deploy-smoke}"
HOST_PORT="${HOST_PORT:-5012}"
API_KEY="${API_KEY:-smoke-test-key}"
ALLOWED_ORIGIN="${ALLOWED_ORIGIN:-http://localhost:${HOST_PORT}}"
TMP_WORKSPACE="$(mktemp -d /tmp/4dpapers-smoke.XXXXXX)"
TMP_PDF="${TMP_WORKSPACE}/export.pdf"

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  rm -rf "${TMP_WORKSPACE}"
}
trap cleanup EXIT

cd "${ROOT_DIR}"

echo "[smoke] Building image ${IMAGE_TAG}"
docker build --build-arg "APP_VERSION=$(cat VERSION)" -t "${IMAGE_TAG}" .

echo "[smoke] Starting container ${CONTAINER_NAME}"
docker run -d --rm \
  --name "${CONTAINER_NAME}" \
  -p "${HOST_PORT}:5006" \
  -e FOURD_API_KEY="${API_KEY}" \
  -e FOURD_ALLOWED_ORIGIN="${ALLOWED_ORIGIN}" \
  -e FOURD_DROP_PRIVILEGES=1 \
  -e FOURD_CHOWN_WORKSPACE=1 \
  -v "${TMP_WORKSPACE}:/workspace" \
  "${IMAGE_TAG}" >/dev/null

echo "[smoke] Waiting for health endpoint"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${HOST_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:${HOST_PORT}/api/health" | grep '"status": "ok"' >/dev/null

echo "[smoke] Verifying process drops to non-root user"
docker exec "${CONTAINER_NAME}" ps -o user= -p 1 | tr -d ' ' | grep '^fourd$' >/dev/null
docker exec "${CONTAINER_NAME}" stat -c '%u:%g' /workspace/main.qmd | grep '^10001:10001$' >/dev/null

echo "[smoke] Verifying authenticated browser-style API access"
curl -fsS --cookie "fourd_api_key=${API_KEY}" "http://127.0.0.1:${HOST_PORT}/api/files" | grep '"main.qmd"' >/dev/null

echo "[smoke] Compiling interactive HTML"
curl -fsS -X POST \
  --cookie "fourd_api_key=${API_KEY}" \
  -H 'Content-Type: application/json' \
  "http://127.0.0.1:${HOST_PORT}/api/compile" \
  -d '{}' | grep '"status": "success"' >/dev/null

echo "[smoke] Compiling PDF export"
curl -fsS -X POST \
  --cookie "fourd_api_key=${API_KEY}" \
  -H 'Content-Type: application/json' \
  "http://127.0.0.1:${HOST_PORT}/api/export" \
  -d '{}' \
  -o "${TMP_PDF}"
head -c 4 "${TMP_PDF}" | grep '%PDF' >/dev/null

echo "[smoke] Verifying protected routes"
mkdir -p "${TMP_WORKSPACE}/state/upload_tmp/probe"
printf 'secret\n' > "${TMP_WORKSPACE}/state/upload_tmp/probe/secret.txt"

test "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HOST_PORT}/output/main.html")" = "401"
test "$(curl -s -o /dev/null -w '%{http_code}' --cookie "fourd_api_key=${API_KEY}" "http://127.0.0.1:${HOST_PORT}/output/main.html")" = "200"
test "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HOST_PORT}/state/upload_tmp/probe/secret.txt")" = "401"
test "$(curl -s -o /dev/null -w '%{http_code}' --cookie "fourd_api_key=${API_KEY}" "http://127.0.0.1:${HOST_PORT}/state/upload_tmp/probe/secret.txt")" = "403"
test "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HOST_PORT}/quick.html")" = "404"
test "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HOST_PORT}/api/quick-target")" = "404"

echo "[smoke] Deployment smoke test passed"
