# 4Dpapers Project Memory

## Project Structure
- `_extensions/4dpaper/4dpaper.py` — pre-render hook, figure generation
- `_extensions/4dpaper/shortcodes.lua` — Quarto shortcode handler
- `dashboard/app.py` — Panel dashboard entry point
- `dashboard/pages/paper_page.py` — Paper tab (iframe + Rebuild HTML + Export PDF)
- `dashboard/utils.py` — shared utilities (quarto render, save/load camera state, pvpython render)
- `analysis_report.qmd` — Quarto paper template with `{{< 4d-image >}}` shortcodes
- `state/figures/` — generated .html and .png figure files (gitignored)
- `state/camera_<fig_id>.json` — per-figure saved camera state (gitignored)
- `tests/` — pytest suite (26+ tests)

## Launch Command
```bash
panel serve dashboard/app.py \
  --plugins dashboard.camera_plugin \
  --static-dirs output=_output \
  --show --port 5006
```
(camera_plugin will be added in Phase 4)

## Current phase: Phase 4 — Camera Sync
Plan: `docs/plans/2026-03-03-phase4-camera-sync.md`

### vtk.js Camera Access (confirmed from bundle inspection)
- `window.renderWindow` is set globally by the bundle via webpack's `n.g = globalThis`
- `window.renderWindow.getInteractor().onEndInteractionEvent(fn)` — end of drag callback
- `window.renderWindow.getRenderers().getFirst().getActiveCamera()` — camera
- Camera API: `.getPosition()`, `.getFocalPoint()`, `.getViewUp()`
- `window.renderWindow` is set synchronously when `OfflineLocalView.load()` is called

### Panel Tornado Integration
- Panel `--plugins dashboard.camera_plugin` reads `ROUTES` from module, adds to Tornado
- `ROUTES = [(r"/camera/(?P<fig_id>[^/]+)", CameraHandler)]`
- No extra port needed — routes added to same Tornado server at port 5006
- srcdoc iframes have `null` origin → need `Access-Control-Allow-Origin: *` on handler

### Already Implemented
- `save_camera_state()` and `load_camera_state()` in `dashboard/utils.py`
- Tests for both in `tests/test_utils.py`

## Key Patterns
- Panel `add_periodic_callback` — always store handle, call `.stop()` before re-registering
- vtk.js HTML: always generates both `.html` AND `.png` (QUARTO_OUTPUT_FORMAT unreliable)
- srcdoc iframe embedding for vtk.js figures (isolated browsing context for window sizing)
- `QUARTO_DOCUMENT_PATH` not always set; fall back to `QUARTO_PROJECT_DIR/*.qmd` scan
- Background threads in Panel: wrap in try/except, always call finish callback with error code

## Test Run Command
```bash
.venv/bin/pytest tests/ -q
```
All tests must pass (currently 26).

## Quarto Render Command
```bash
QUARTO_PYTHON=.venv/bin/python quarto render analysis_report.qmd --to html
```
