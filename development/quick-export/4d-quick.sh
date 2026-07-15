#!/usr/bin/env bash
# =============================================================================
# 4d-quick.sh — isolated Quick Export launcher for 4Dpapers
#
# Usage:
#   ./development/quick-export/4d-quick.sh <path-to-simulation-case-or-file> [options]
#
# Examples:
#   ./development/quick-export/4d-quick.sh ~/simulations/aorta/
#   ./development/quick-export/4d-quick.sh ~/data/heart.vtu --port 5008
#
# What it does:
#   1. Validates the target path
#   2. Creates a disposable workspace and mounts the target source read-only
#   3. Waits for the server to become healthy
#   4. Opens quick.html in Chrome/Edge App Mode (native-feeling window)
#   5. Retains only the figure HTML and standalone document HTML
#   6. Stops the container and deletes the disposable workspace on Ctrl-C
# =============================================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; NC='\033[0m'

# ── Argument parsing ──────────────────────────────────────────────────────────
TARGET_ARG=""
OUTPUT_ARG=""
PORT=5007
OPEN_BROWSER=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port|-p)
      if [[ $# -lt 2 ]]; then
        echo -e "${RED}Error: $1 requires a value.${NC}" >&2
        exit 1
      fi
      PORT="$2"; shift 2 ;;
    --output-dir|-o)
      if [[ $# -lt 2 ]]; then
        echo -e "${RED}Error: $1 requires a value.${NC}" >&2
        exit 1
      fi
      OUTPUT_ARG="$2"; shift 2 ;;
    --no-browser) OPEN_BROWSER=0; shift ;;
    --help|-h)
      echo "Usage: $0 <path-to-simulation> [options]"
      echo ""
      echo "  Opens Quick Export for the given simulation case or file."
      echo "  Supported formats: .foam, .vtu, .vtp, .stl, .obj, .ply, .exo, .xdmf, …"
      echo ""
      echo "  Options:"
      echo "    --port PORT         Port to expose (default: 5007)"
      echo "    --output-dir DIR    Retained HTML directory"
      echo "                        (default: <source-parent>/4dpapers-exports)"
      echo "    --no-browser        Start without opening a browser"
      exit 0 ;;
    -*) echo -e "${RED}Unknown option: $1${NC}" >&2; exit 1 ;;
    *)  TARGET_ARG="$1"; shift ;;
  esac
done

if [[ -z "$TARGET_ARG" ]]; then
  echo -e "${RED}Error: no target specified.${NC}" >&2
  echo "Usage: $0 <path-to-simulation-case-or-file> [options]" >&2
  exit 1
fi

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo -e "${RED}Error: port must be an integer between 1 and 65535.${NC}" >&2
  exit 1
fi

# ── Resolve paths ─────────────────────────────────────────────────────────────
TARGET=$(realpath "$TARGET_ARG" 2>/dev/null) || {
  echo -e "${RED}Error: path not found: $TARGET_ARG${NC}" >&2
  exit 1
}

if [[ ! -e "$TARGET" ]]; then
  echo -e "${RED}Error: path not found: $TARGET${NC}" >&2
  exit 1
fi

SOURCE_ROOT=$(dirname "$TARGET")
BASENAME=$(basename "$TARGET")
QUICK_TARGET="/workspace/source/${BASENAME}"

if [[ -n "$OUTPUT_ARG" ]]; then
  mkdir -p "$OUTPUT_ARG"
  OUTPUT_DIR=$(cd "$OUTPUT_ARG" && pwd -P)
else
  OUTPUT_DIR="${SOURCE_ROOT}/4dpapers-exports"
  mkdir -p "$OUTPUT_DIR"
  OUTPUT_DIR=$(cd "$OUTPUT_DIR" && pwd -P)
fi

if [[ "$SOURCE_ROOT" == "$OUTPUT_DIR" || "$SOURCE_ROOT" == "$OUTPUT_DIR"/* ]]; then
  echo -e "${RED}Error: output directory must be dedicated and must not contain the source.${NC}" >&2
  exit 1
fi

if [[ -d "$TARGET" && ( "$OUTPUT_DIR" == "$TARGET" || "$OUTPUT_DIR" == "$TARGET"/* ) ]]; then
  echo -e "${RED}Error: output directory must not be inside the read-only source case.${NC}" >&2
  exit 1
fi

CONTAINER_NAME="4dpapers-quick-${PORT}"
IMAGE="${IMAGE:-4dpapers-local}"
URL="http://localhost:${PORT}/quick.html"
RUNTIME_WORKSPACE=""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}4Dpapers — Quick Export${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Target:   ${TARGET}${NC}"
echo -e "${GREEN}Source:   ${SOURCE_ROOT} (read-only)${NC}"
echo -e "${GREEN}HTML out: ${OUTPUT_DIR}${NC}"
echo -e "${GREEN}Container target: ${QUICK_TARGET}${NC}"
echo -e "${GREEN}Port:     ${PORT}${NC}"
echo -e "${GREEN}Image:    ${IMAGE}${NC}"
echo ""

# ── Preflight: Docker available + image built ─────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo -e "${RED}Error: 'docker' not found on PATH.${NC}" >&2
  echo -e "${YELLOW}Install Docker Desktop (or the Docker engine) and try again.${NC}" >&2
  exit 1
fi

if ! docker info &>/dev/null; then
  echo -e "${RED}Error: cannot talk to the Docker daemon.${NC}" >&2
  echo -e "${YELLOW}Is Docker running? Start Docker Desktop and try again.${NC}" >&2
  exit 1
fi

if ! docker image inspect "$IMAGE" &>/dev/null; then
  echo -e "${RED}Error: Docker image '${IMAGE}' not found.${NC}" >&2
  echo -e "${YELLOW}Build it first from the repo root:${NC}" >&2
  echo -e "    docker compose build" >&2
  echo -e "${YELLOW}(or set IMAGE=<your-image> if you built it under a different name)${NC}" >&2
  exit 1
fi

if ! docker run --rm --entrypoint /usr/bin/test "$IMAGE" \
  -f /app/development/quick-export/backend_handlers.py; then
  echo -e "${RED}Error: Docker image '${IMAGE}' does not contain the isolated Quick Export module.${NC}" >&2
  echo -e "${YELLOW}Rebuild it from the current repository: docker compose build${NC}" >&2
  exit 1
fi

RUNTIME_WORKSPACE=$(mktemp -d "${TMPDIR:-/tmp}/4dpapers-quick.XXXXXX")
mkdir -p "${RUNTIME_WORKSPACE}/source"

# ── Cleanup trap ──────────────────────────────────────────────────────────────
cleanup() {
  trap - EXIT INT TERM
  echo ""
  echo -e "${YELLOW}Stopping container…${NC}"
  docker stop "$CONTAINER_NAME" &>/dev/null || true
  if [[ -n "$RUNTIME_WORKSPACE" && -d "$RUNTIME_WORKSPACE" ]]; then
    rm -rf "$RUNTIME_WORKSPACE"
  fi
  echo -e "${GREEN}✓ Done.${NC}"
  echo -e "${GREEN}Retained HTML: ${OUTPUT_DIR}${NC}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ── Stop any leftover container with the same name ────────────────────────────
if docker inspect "$CONTAINER_NAME" &>/dev/null 2>&1; then
  echo -e "${YELLOW}Stopping existing container ${CONTAINER_NAME}…${NC}"
  docker stop "$CONTAINER_NAME" &>/dev/null || true
  docker rm   "$CONTAINER_NAME" &>/dev/null || true
fi

# ── Start container ───────────────────────────────────────────────────────────
echo -e "${YELLOW}Starting container…${NC}"
docker run -d \
  --rm \
  --name  "$CONTAINER_NAME" \
  --user  "$(id -u):$(id -g)" \
  -p      "127.0.0.1:${PORT}:5006" \
  -v      "${RUNTIME_WORKSPACE}:/workspace" \
  -v      "${SOURCE_ROOT}:/workspace/source:ro" \
  -v      "${OUTPUT_DIR}:/quick-output" \
  -e      "PORT=5006" \
  -e      "FOURD_ALLOW_INSECURE=1" \
  -e      "FOURD_QUICK_TARGET=${QUICK_TARGET}" \
  -e      "FOURD_QUICK_OUTPUT=/quick-output" \
  -e      "HOME=/workspace/.home" \
  -e      "XDG_CACHE_HOME=/workspace/.home/.cache" \
  -e      "XDG_CONFIG_HOME=/workspace/.home/.config" \
  -e      "PYTHONUNBUFFERED=1" \
  -e      "PROJECT_ROOT=/workspace" \
  -e      "PYVISTA_OFF_SCREEN=true" \
  -e      "VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN=1" \
  "$IMAGE" > /dev/null

echo -e "${GREEN}✓ Container started: ${CONTAINER_NAME}${NC}"

# ── Wait for health ───────────────────────────────────────────────────────────
echo -e "${YELLOW}Waiting for server to start…${NC}"
ATTEMPTS=0
MAX_ATTEMPTS=60
until curl -sf "http://localhost:${PORT}/api/health" > /dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [[ $ATTEMPTS -ge $MAX_ATTEMPTS ]]; then
    echo -e "${RED}Error: server did not start within 60 seconds.${NC}" >&2
    echo -e "${YELLOW}Container logs:${NC}" >&2
    docker logs "$CONTAINER_NAME" --tail 30 >&2
    exit 1
  fi
  sleep 1
done
echo -e "${GREEN}✓ Server ready at ${URL}${NC}"
echo ""

# ── Open browser in App Mode ──────────────────────────────────────────────────
_open_browser() {
  local url="$1"

  # macOS Chrome
  local chrome_mac="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  if [[ -x "$chrome_mac" ]]; then
    "$chrome_mac" --app="$url" --no-first-run 2>/dev/null &
    return 0
  fi

  # Linux / PATH Chrome
  for cmd in google-chrome google-chrome-stable; do
    if command -v "$cmd" &>/dev/null; then
      "$cmd" --app="$url" --no-first-run 2>/dev/null &
      return 0
    fi
  done

  # Chromium
  for cmd in chromium-browser chromium; do
    if command -v "$cmd" &>/dev/null; then
      "$cmd" --app="$url" --no-first-run 2>/dev/null &
      return 0
    fi
  done

  # macOS Edge
  local edge_mac="/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
  if [[ -x "$edge_mac" ]]; then
    "$edge_mac" --app="$url" --no-first-run 2>/dev/null &
    return 0
  fi

  # Linux / PATH Edge
  for cmd in microsoft-edge msedge; do
    if command -v "$cmd" &>/dev/null; then
      "$cmd" --app="$url" --no-first-run 2>/dev/null &
      return 0
    fi
  done

  # macOS fallback — default browser (no app mode)
  if command -v open &>/dev/null; then
    echo -e "${YELLOW}No Chrome/Edge found — opening in default browser (no App Mode).${NC}"
    open "$url"
    return 0
  fi

  # Linux fallback
  if command -v xdg-open &>/dev/null; then
    echo -e "${YELLOW}No Chrome/Edge found — opening in default browser (no App Mode).${NC}"
    xdg-open "$url" 2>/dev/null &
    return 0
  fi

  echo -e "${YELLOW}Could not detect a browser. Open manually: ${url}${NC}"
}

if [[ "$OPEN_BROWSER" == "1" ]]; then
  _open_browser "$URL"
fi

echo -e "${BLUE}Quick Export is running.${NC}"
echo -e "${GREEN}Only HTML artifacts will be retained in ${OUTPUT_DIR}.${NC}"
echo -e "${YELLOW}Press Ctrl-C to stop.${NC}"
echo ""

# ── Keep alive until Ctrl-C ───────────────────────────────────────────────────
# Use wait on a background tail so the trap fires on INT/TERM
tail -f /dev/null &
TAIL_PID=$!
wait $TAIL_PID
