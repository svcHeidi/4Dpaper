# PVSM Figure Support Design

**Goal:** Add a `{{< 4d-pvsm >}}` shortcode that replays a ParaView state file (`.pvsm`) to produce interactive vtk.js HTML figures and high-quality PDF screenshots, using the same camera-sync and rebuild workflow as existing figure types.

**Architecture:** pvpython loads the PVSM and exports (a) the pipeline output as a `.vtp` mesh and (b) a PDF screenshot in one subprocess call. PyVista then loads the `.vtp` and calls `export_html()` to produce the vtk.js interactive figure. No PVSM-to-PyVista translation layer — pvpython applies the pipeline exactly, PyVista handles the browser export.

**Tech Stack:** ParaView pvpython (`paraview.simple`), PyVista, Python `xml.etree.ElementTree` (color map extraction), existing `shortcodes.lua` / `4dpaper.py` / camera-sync infrastructure.

---

## Shortcode Syntax

```
{{< 4d-pvsm src="fig-vm.pvsm" id="fig-vm" caption="Transmembrane voltage, clipped" >}}
```

`src` is the only required parameter — path to the `.pvsm` file, relative to the QMD document.

Optional overrides:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `data` | (from PVSM) | Override the OpenFOAM reader path inside the PVSM at runtime |
| `time` | (from PVSM) | Override animation timestep: `"last"`, `"mid"`, or float e.g. `"0.05"` |
| `caption` | `""` | Figure caption |

No `field=` parameter — the active field is part of the PVSM pipeline definition. Different field = different PVSM.

---

## File Structure

New files created or modified:

```
_extensions/4dpaper/
├── 4dpaper.py              ← MODIFY: parse_pvsm_shortcodes(), generate_pvsm_figure(),
│                                      generate_html_from_vtp(), pvsm color map helpers
└── pvsm_render.py          ← NEW: pvpython-only script, called as subprocess

_extensions/4dpaper/shortcodes.lua   ← MODIFY: fourd_pvsm() handler, register "4d-pvsm"

state/figures/              ← runtime outputs (gitignored)
├── {id}-pipeline.vtp       ← intermediate: pvpython pipeline output mesh
├── {id}.html               ← vtk.js interactive figure (from PyVista + .vtp)
├── {id}.png                ← PDF screenshot (from pvpython SaveScreenshot)
└── {id}-preview.html       ← camera-setup preview (vtk.js, no locked camera)

tests/
└── test_pvsm.py            ← NEW: unit tests for PVSM parsing and pipeline
```

---

## Pre-render Flow

For each `4d-pvsm` shortcode detected in the QMD, `4dpaper.py` runs:

```
PVSM file
camera_<id>.json (optional)
        │
        ▼
[1] subprocess: pvpython pvsm_render.py
        ├── LoadState(pvsm)
        ├── patch FileName if --data given
        ├── set AnimationTime if --time given
        ├── find last visible pipeline filter
        ├── SaveData(id-pipeline.vtp)       ← clipped/filtered geometry
        ├── apply camera from JSON if given
        └── SaveScreenshot(id.png)          ← high-res PDF render
        │
        ▼
[2] PyVista in-process
        ├── pyvista.read(id-pipeline.vtp)
        ├── extract scalar name + range from PVSM XML
        ├── add_mesh(scalars=..., clim=...)
        ├── apply camera from JSON if given
        ├── export_html(id.html)            ← interactive vtk.js
        └── export_html(id-preview.html)    ← camera-setup preview (no locked camera)
```

---

## `pvsm_render.py` — pvpython script

CLI interface (called via `pvpython pvsm_render.py <args>`):

```
--pvsm         PATH    required  path to .pvsm file
--out-vtp      PATH    required  where to write pipeline output mesh
--out-png      PATH    required  where to write PDF screenshot
--data         PATH    optional  override OpenFOAMReader FileName in PVSM
--time         FLOAT   optional  override animation timestep
--camera       PATH    optional  JSON file with CameraPosition/FocalPoint/ViewUp
--resolution   W H     optional  screenshot resolution (default 3840 2160)
```

Internal steps:

1. `LoadState(pvsm)` — loads the full pipeline including all filters
2. If `--data`: iterate `GetSources()`, find proxy where `proxy.GetProperty("FileName")` exists, set it to the new path, call `proxy.UpdatePipeline()`
3. If `--time`: `GetAnimationScene().AnimationTime = float(time)`
4. Find the last visible source: iterate `GetSources()`, pick the one that is visible in the active view and has no downstream consumers
5. `SaveData(out_vtp, proxy=last_visible)` — exports VTK PolyData/UnstructuredGrid
6. If `--camera`: load JSON, `view.CameraPosition = [...]`, `view.CameraFocalPoint = [...]`, `view.CameraViewUp = [...]`, `Render()`
7. `SaveScreenshot(out_png, view, ImageResolution=[W, H])`

---

## `generate_html_from_vtp()` — PyVista HTML export

New function in `4dpaper.py`:

```python
def generate_html_from_vtp(
    vtp_path: Path,
    out_html: Path,
    fig_id: str,
    pvsm_path: Path,
    preview: bool = False,
) -> None
```

Steps:

1. `mesh = pyvista.read(vtp_path)` — loads the pipeline output geometry
2. Extract color info from PVSM XML with `xml.etree.ElementTree`:
   - Active scalar name: `ColorArrayName` property on the last representation proxy
   - Scalar range: `RGBPoints` first/last values from the LookupTable proxy
   - Color map name: `Preset` property (e.g. `"Cool to Warm"`) — mapped to matplotlib equivalents
3. `pl = pyvista.Plotter(off_screen=True)`
4. `pl.add_mesh(mesh, scalars=scalar_name, clim=[vmin, vmax], cmap=cmap)`
5. If not `preview` and camera JSON exists: apply saved camera
6. `pl.export_html(out_html)`

Color map fallback: if the PVSM's preset name has no matplotlib equivalent, default to `"coolwarm"`.

---

## Cache Invalidation

Regenerate when any dependency is newer than the outputs:

```
dependencies:  PVSM mtime, data file mtime (if --data given), camera JSON mtime, 4dpaper.py mtime
outputs:       id-pipeline.vtp, id.html, id.png, id-preview.html
```

Logic mirrors `is_cache_valid()` used for `4d-image` and `4d-video`. A single check covers all four outputs — if any is missing or stale, all four are regenerated together.

Note: camera change triggers full regeneration (both `.vtp` + `.html` + `.png`). This is slightly over-eager (camera doesn't affect geometry) but keeps the logic simple and consistent with other figure types.

---

## `shortcodes.lua` — `fourd_pvsm()` handler

Identical structure to `fourd_image()`:

- **HTML output (app mode):** `<iframe src="/state/figures/{id}.html">` with cache-busting `?t=Date.now()` via inline JS (same pattern as `4d-video`)
- **HTML output (export mode):** srcdoc with escaped HTML content
- **PDF output:** `pandoc.Image` pointing to `state/figures/{id}.png`
- **Camera button:** injected at paper level (same as `4d-video` — avoids compositor layer issue)
- **Relay script:** shared `_RELAY_SCRIPT` injection, same `_relay_injected` guard

Registered at the bottom of `shortcodes.lua`:
```lua
["4d-pvsm"] = fourd_pvsm,
```

---

## Camera Sync

No changes to the camera sync system. The camera overlay, postMessage relay, `/camera/<fig_id>` endpoint, and `state/camera_<fig_id>.json` all work identically. The preview HTML (`id-preview.html`) is a standard vtk.js export with no locked camera — the user rotates, the badge goes green, camera is saved to JSON. Next rebuild applies it to both pvpython screenshot and PyVista HTML.

---

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| pvpython not found | Print path hint, `sys.exit(1)` — hard error, rebuild fails |
| PVSM file missing | Print clear message with path, `sys.exit(1)` |
| `SaveData` produces empty mesh | Warning + skip HTML generation; PNG still produced |
| Color map not in matplotlib | Fallback to `"coolwarm"`, log warning |
| Camera JSON malformed | Log warning, use PVSM's baked-in camera |

---

## Testing

`tests/test_pvsm.py` covers:

1. PVSM XML parsing — correct scalar name, range, and color map extracted from `example_state.pvsm`
2. `pvsm_render.py` CLI argument parsing — all flags parsed correctly
3. End-to-end smoke test: run `pvsm_render.py` against `example_state.pvsm`, verify `.vtp` and `.png` are produced and non-empty
4. `generate_html_from_vtp()` — loads the `.vtp` produced above, verify `.html` is produced and contains vtk.js markers
5. Cache invalidation — touching PVSM triggers regeneration; touching unrelated file does not

Tests that require pvpython are marked `@pytest.mark.skipif(not pvpython_available(), ...)` so CI without ParaView can still run the parsing and HTML tests.
