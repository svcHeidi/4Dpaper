# Isolated Quick Export

Quick Export turns one supported simulation file or OpenFOAM case into an
interactive figure HTML and a self-contained document HTML without creating a
paper project beside the source data.

## How isolation works

The launcher creates a temporary host directory and mounts it as the writable
4Dpapers workspace. It mounts the source directory separately at
`/workspace/source` with Docker read-only permissions, preserving adjacent
companions such as XDMF/HDF5 files and complete OpenFOAM case directories.

A dedicated output directory is the only persistent writable mount. Quick mode
generates no PNG and retains only:

- `fig-<name>.html` — the interactive figure used by the preview.
- `<title>-standalone.html` — the portable document with the figure embedded.

The browser also downloads the standalone document. Stopping the launcher
removes the container and temporary workspace, including QMD, Quarto cache,
state, media, and intermediate output.

Quick routes are opt-in. `serve.py` loads them only when
`FOURD_QUICK_TARGET` is set, so the normal dashboard continues to return 404
for `/quick.html` and `/api/quick-target`.

## Run it

Build the current image, then provide a supported file or `.foam` marker:

```bash
docker compose build
./development/quick-export/4d-quick.sh /path/to/result.vtu
```

By default, retained files go to `4dpapers-exports/` beside the source. Choose
another dedicated location with:

```bash
./development/quick-export/4d-quick.sh /path/to/case.foam \
  --output-dir /path/to/exports
```

Set `IMAGE=ghcr.io/4dpapers/4dpapers:0.1.1` to use the tagged image once it is
published. Use `--no-browser` for automation.

## 2026-07-14 verification

- Unit and integration subset: `30 passed, 1 skipped`.
- Full regression suite: `403 passed, 11 skipped`.
- Chromium Quick/standalone E2E: `2 passed` for the VTK audit.
- VTK: preview and 1.1 MB standalone export passed; live canvases appeared.
- OpenFOAM: a real local `cube_structured.foam` case previewed and exported;
  the retained standalone opened with a live canvas.
- Both source manifests were byte-identical before and after their runs.
- Docker reported the source mount `rw=false` and output mount `rw=true`.
- The temporary workspace no longer existed after launcher shutdown.
- Normal mode remained healthy and returned 404 for the Quick page and API.

Before the public announcement, repeat the same test with the intended launch
case and the published multi-architecture image from a clean clone.

## Contents

- `4d-quick.sh` — isolated local launcher.
- `quick.html` — single-dataset interface.
- `backend_handlers.py` — opt-in page and API routes.
- `test_quick_export_launcher.py` — isolation and route regression checks.
