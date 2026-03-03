# Phase 4 — Camera Sync Design

**Date:** 2026-03-03
**Status:** Approved

---

## Problem

The HTML interactive viewer and the PDF PNG figures are disconnected. The user rotates the 3D mesh in the browser but the PDF always uses a hardcoded isometric angle. The core value of the extension is "what you see in the browser is what you get in the PDF."

---

## Goal

Auto-sync the vtk.js camera from the browser to the server whenever the user rotates a figure. When "Export PDF" is clicked, each figure's PNG is regenerated with the saved camera angle. If no camera has been saved, fall back to the default isometric view.

---

## Architecture

```
User rotates figure in browser
    → vtk.js canvas "mouseup" → debounced JS handler (500ms)
    → fetch POST to http://localhost:5006/camera/<fig_id>
         body: { position, focal_point, view_up }
    → Tornado RequestHandler writes state/camera_<fig_id>.json

"Export PDF" clicked
    → run_quarto_render(..., output_format="pdf")
    → pre-render hook (4dpaper.py) runs for each figure
    → checks state/camera_<fig_id>.json mtime vs state/figures/<fig_id>.png mtime
    → if camera JSON is newer → regenerate PNG with PyVista using saved camera
    → Quarto renders PDF with updated PNGs → download link
```

---

## Camera State Format

Per-figure JSON saved to `state/camera_<fig_id>.json`:

```json
{
  "position":    [x, y, z],
  "focal_point": [x, y, z],
  "view_up":     [x, y, z]
}
```

---

## Files Changed

### `_extensions/4dpaper/4dpaper.py`

**`generate_html_figure()`** — after `pl.export_html()`, inject a JS snippet into the generated HTML:
- Hook `mouseup` on the vtk.js canvas (debounced 500ms)
- Read `renderer.getActiveCamera()` → `position`, `focalPoint`, `viewUp`
- POST to `http://localhost:5006/camera/<fig_id>` as JSON
- Update a small overlay badge: `📷 Camera synced` (green) / `📷 Default view` (grey)

**`generate_png_figure()`** — before `pl.isometric_view()`:
- Check `state/camera_<fig_id>.json` exists
- If yes: apply `pl.camera.position`, `pl.camera.focal_point`, `pl.camera.view_up`
- If no: fall back to `pl.isometric_view()`

**`is_cache_valid()`** — extend to accept an optional `camera_path`:
- PNG is stale if `camera_<fig_id>.json` is newer than `<fig_id>.png`

**`main()`** — pass `fig_id` to `generate_png_figure()` so it can load the right camera file.

### `dashboard/app.py`

Add a Tornado `RequestHandler` at `/camera/(?P<fig_id>[^/]+)`:
- Accepts POST with JSON body `{position, focal_point, view_up}`
- Writes to `state/camera_<fig_id>.json`
- Returns 200 JSON `{"status": "ok"}`

Register the handler in `pn.serve()` call or via `pn.state.onload` + Bokeh server hooks.

### `state/`

New per-figure camera files: `state/camera_<fig_id>.json` (gitignored).

---

## UI

- Small overlay badge injected into each vtk.js figure HTML
- `📷 Default view` (grey) initially
- `📷 Camera synced` (green) after first rotation
- No new dashboard buttons needed

---

## What Does NOT Change

- Dashboard Paper tab layout (HTML iframe + Rebuild HTML + Export PDF)
- `shortcodes.lua` Lua shortcode handler
- Run/post-processing tab
- `analysis_report.qmd` template
- `dashboard/utils.py` (no changes needed)
- `dashboard/pages/paper_page.py` (no changes needed)

---

## Scope Boundary

The run/post-processing tab and outputs page are out of scope. This phase is camera sync only.
