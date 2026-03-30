# PVSM Figure Support Design

**Goal:** Add a `{{< 4d-pvsm >}}` shortcode that replays a ParaView state file (`.pvsm`) to produce interactive vtk.js HTML figures and high-quality PDF screenshots, using the same camera-sync and rebuild workflow as existing figure types.

**Architecture:** pvpython loads the PVSM and exports (a) the pipeline output as a `.vtu` mesh and (b) a PDF screenshot in one subprocess call. PyVista then loads the `.vtu` and calls `export_html()` to produce the vtk.js interactive figure. No PVSM-to-PyVista translation layer — pvpython applies the pipeline exactly, PyVista handles the browser export.

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

```
_extensions/4dpaper/
├── 4dpaper.py              ← MODIFY: parse_pvsm_shortcodes(), generate_pvsm_figure(),
│                                      generate_html_from_vtu(), pvsm color map helpers
└── pvsm_render.py          ← NEW: pvpython-only script, called as subprocess

_extensions/4dpaper/shortcodes.lua   ← MODIFY: fourd_pvsm() handler, register "4d-pvsm"

state/figures/              ← runtime outputs (gitignored)
├── {id}-pipeline.vtu       ← intermediate: pvpython pipeline output mesh (UnstructuredGrid)
├── {id}.html               ← vtk.js interactive figure (from PyVista + .vtu)
├── {id}.png                ← PDF screenshot (from pvpython SaveScreenshot)
└── {id}-preview.html       ← camera-setup preview (vtk.js, no locked camera)

tests/
└── test_pvsm.py            ← NEW: unit tests for PVSM parsing and pipeline
```

Note: intermediate format is `.vtu` (VTK UnstructuredGrid XML), not `.vtp` (PolyData). ParaView's Clip filter on OpenFOAM data produces `vtkUnstructuredGrid`, which cannot be saved as `.vtp`. PyVista reads `.vtu` natively.

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
        ├── patch OpenFOAMReader FileName if --data given (UpdatePipeline after)
        ├── set AnimationTime if --time given (UpdatePipeline after)
        ├── find last visible filter (see algorithm below)
        ├── SaveData(id-pipeline.vtu)      ← clipped/filtered geometry
        ├── apply camera from JSON if given (else use PVSM baked-in camera)
        └── SaveScreenshot(id.png)         ← high-res PDF render
        │
        ▼
[2] PyVista in-process (4dpaper.py)
        ├── pyvista.read(id-pipeline.vtu)
        ├── extract scalar name + range from PVSM XML (see color map section)
        ├── add_mesh(scalars=..., clim=..., preference='point' or 'cell')
        ├── apply camera from JSON if given (else isometric — see initial viewpoint note)
        ├── export_html(id.html)           ← interactive vtk.js
        └── export_html(id-preview.html)   ← camera-setup preview (no locked camera)
```

**Initial viewpoint note:** On first run (no camera JSON), the PDF figure uses the PVSM's baked-in camera; the HTML figure uses PyVista's isometric default. These will differ. This is expected and intentional — the user sets the shared camera via the overlay after first build, and subsequent rebuilds apply it to both. The spec does not auto-extract the PVSM camera to JSON on first run; that would override the user's subsequent choice.

---

## `pvsm_render.py` — pvpython script

CLI interface:

```
--pvsm         PATH       required  path to .pvsm file
--out-vtu      PATH       required  where to write pipeline output mesh (.vtu)
--out-png      PATH       required  where to write PDF screenshot
--data         PATH       optional  override OpenFOAMReader FileName in PVSM
--time         VALUE      optional  timestep: float, "last", or "mid"
--camera       PATH       optional  JSON with CameraPosition/FocalPoint/ViewUp
--resolution   W H        optional  screenshot resolution (default 3840 2160)
```

Internal steps in order:

1. `LoadState(pvsm)` — loads full pipeline
2. If `--data`: find the OpenFOAMReader proxy by iterating `GetSources()` and checking `proxy.GetXMLName() == "OpenFOAMReader"` (not by checking for a `FileName` property, which exists on many proxy types). Set `proxy.FileName = data_path`. Call `proxy.UpdatePipeline()`.
3. If `--time`:
   - `"last"` → `GetAnimationScene().GoToLast()`
   - `"mid"` → `scene = GetAnimationScene(); mid = (scene.StartTime + scene.EndTime) / 2; scene.AnimationTime = mid`
   - float string → `GetAnimationScene().AnimationTime = float(value)`
   - After any time change: call `GetActiveView().Update()` to propagate
4. **Find last visible filter** — algorithm:
   - `view = GetActiveViewOrCreate('RenderView')`
   - `reps = view.Representations` — list of representation proxies in the view
   - Filter to those where `rep.Visibility == 1`
   - For each visible rep, get its input source: `source = rep.Input[0]` — `rep.Input` is a `ProxyProperty`; index 0 gives the actual source proxy
   - Among visible sources, pick the one that is not itself the `Input` of any other visible source — this is the terminal (leaf) filter
   - If multiple leaves exist, pick the one with the highest pipeline depth (count hops from reader to source)
5. `writer = servermanager.CreateWriter(out_vtu, source)` or `SaveData(out_vtu, proxy=source)` — saves as VTK UnstructuredGrid XML (`.vtu`)
6. Verify the written file: open it, check `<NumberOfPoints` attribute > 0; if zero, print warning and exit non-zero
7. If `--camera`: load JSON, set `view.CameraPosition`, `view.CameraFocalPoint`, `view.CameraViewUp`, call `Render()`
8. `SaveScreenshot(out_png, view, ImageResolution=[W, H])`

---

## Color Map Extraction from PVSM XML

`4dpaper.py` parses the PVSM XML with `xml.etree.ElementTree` to extract color information for the PyVista HTML figure. All parsing is done in `4dpaper.py` (not in the pvpython script).

### Active scalar name and field association

Find the representation proxy for the last visible filter by walking the PVSM XML: search all `<Proxy group="representations" type="GeometryRepresentation">` nodes, find the one whose `<Property name="Input"><Proxy value="SOURCE_ID"/>` references the target source proxy id (determined by the same leaf-detection logic applied to the XML pipeline graph). Then read color properties from that representation node. Locate its `ColorArrayName` property:

```xml
<Property name="ColorArrayName" number_of_elements="5">
  <Element index="0" value=""/>
  <Element index="1" value=""/>
  <Element index="2" value=""/>
  <Element index="3" value="1"/>   <!-- field association: 1=point, 0=cell -->
  <Element index="4" value="Vm"/> <!-- scalar array name -->
</Property>
```

- Scalar name = `elements[4].get('value')`
- Field association = `'point'` if `elements[3].get('value') == '1'` else `'cell'`
- Pass `preference=field_association` to `pl.add_mesh()`

### Scalar range

Find the `PVLookupTable` proxy linked to the representation's `LookupTable` property. Extract `RGBPoints`:

```xml
<Property name="RGBPoints" number_of_elements="32">
  <Element index="0" value="-85.0"/>   <!-- first scalar value -->
  <Element index="1" value="0.23"/>    <!-- R -->
  <Element index="2" value="0.30"/>    <!-- G -->
  <Element index="3" value="0.75"/>    <!-- B -->
  ...
  <Element index="28" value="40.0"/>   <!-- last scalar value -->
  ...
</Property>
```

- `vmin = float(elements[0].get('value'))`
- `vmax = float(elements[-4].get('value'))` (last group of 4, index 0)
- `clim = [vmin, vmax]`

### Color map (preset)

Check `NameOfLastPresetApplied` property on the `PVLookupTable` proxy. If non-empty, map to matplotlib equivalent (e.g. `"Cool to Warm"` → `"coolwarm"`, `"Viridis (matplotlib)"` → `"viridis"`). If empty or unmapped (the common case for customized color maps), build a `matplotlib.colors.LinearSegmentedColormap` from the `RGBPoints` control points:

```python
# RGBPoints is a flat list: [scalar, R, G, B, scalar, R, G, B, ...]
points = [(rgb[0], (rgb[1], rgb[2], rgb[3])) for rgb in chunked(rgb_points, 4)]
# Normalize scalar values to [0, 1]
norm_points = [(s - vmin) / (vmax - vmin) for s, _ in points]
cmap = LinearSegmentedColormap.from_list('pvsm', list(zip(norm_points, [c for _, c in points])))
```

Pass this `cmap` object to `pl.add_mesh(cmap=cmap)`. This preserves the PVSM's actual color scale including custom diverging maps and non-standard presets.

---

## `generate_html_from_vtu()` — PyVista HTML export

New function in `4dpaper.py`:

```python
def generate_html_from_vtu(
    vtu_path: Path,
    out_html: Path,
    fig_id: str,
    scalar_name: str,
    clim: list[float],
    cmap,                  # str name or LinearSegmentedColormap
    field_association: str,  # 'point' or 'cell'
    preview: bool = False,
) -> None
```

Steps:
1. `mesh = pyvista.read(vtu_path)` — reads the pipeline output geometry
2. `pl = pyvista.Plotter(off_screen=False)` — `export_html()` requires the WebGL exporter which is only initialised when `off_screen=False`; matches the pattern used by all other figure generators in `4dpaper.py`
3. `pl.add_mesh(mesh, scalars=scalar_name, clim=clim, cmap=cmap, preference=field_association)`
4. If not `preview` and `state/camera_{fig_id}.json` exists: apply saved camera
5. `pl.export_html(out_html)`

---

## Cache Invalidation

Regenerate when any dependency is newer than the outputs:

```
dependencies:
  - PVSM file mtime
  - data file mtime (if --data given; extracted from PVSM FileName if not overridden)
  - camera JSON mtime  (state/camera_{id}.json)
  - 4dpaper.py mtime
  - pvsm_render.py mtime   ← included so script changes trigger regeneration

outputs (all regenerated together if any is stale):
  - {id}-pipeline.vtu
  - {id}.html
  - {id}.png
  - {id}-preview.html
```

The existing `is_cache_valid(fig_path, src_path, camera_path, field_path)` only accepts one `src_path`. For PVSM figures, extend `is_cache_valid()` with an `extra_deps: list[Path] | None = None` parameter that appends additional mtime checks. Pass `extra_deps=[pvsm_render_py_path]` when calling it. The `4dpaper.py` mtime check (already present for other figure types via `script_newer` logic) applies here the same way.

Camera change triggers full regeneration (including geometry re-export) for simplicity — same pattern as other figure types.

---

## `shortcodes.lua` — `fourd_pvsm()` handler

In **app mode** (HTML preview in dashboard): follows the `fourd_video` pattern exactly — the camera button is injected at paper level (in `analysis_report.html`'s DOM) via a `<div style="position:relative">` wrapper with an inline `<button>` whose `onclick` directly calls `document.getElementById('fourd-cam-overlay')`. This avoids the video compositor layer issue. The iframe itself is loaded with a cache-busting `?t=Date.now()` via inline JS.

In **export mode** (standalone HTML): iframe content is inlined as `srcdoc` (escaped HTML), same as `fourd_image`. No camera button in export mode.

In **PDF output**: `pandoc.Image` pointing to `state/figures/{id}.png`.

Relay script injection: shared `_RELAY_SCRIPT`, same `_relay_injected` guard.

`fourd_pvsm` follows the full structure of `fourd_image` and `fourd_video` including the "not yet rendered" early-return guard: if `state/figures/{id}.html` does not exist (first run before any rebuild), return a styled placeholder div rather than an empty or broken iframe.

Registered at bottom of `shortcodes.lua`:
```lua
["4d-pvsm"] = fourd_pvsm,
```

---

## Camera Sync

No changes to the camera sync system. The overlay, relay, `/camera/<fig_id>` endpoint, and `state/camera_<fig_id>.json` all work identically. The preview HTML (`id-preview.html`) is a vtk.js export with no locked camera. Camera is applied to both pvpython (`SaveScreenshot`) and PyVista (`export_html`) on the next rebuild.

---

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| pvpython not found | Print path hint, `sys.exit(1)` |
| PVSM file missing | Print clear message with path, `sys.exit(1)` |
| `SaveData` produces zero-point mesh | `pvsm_render.py` exits non-zero; `4dpaper.py` logs error and skips HTML |
| No visible source found in PVSM | `pvsm_render.py` exits non-zero with explanation |
| Color map extraction fails | Fallback to `"coolwarm"` + full scalar range, log warning |
| Camera JSON malformed | Log warning, use PVSM's baked-in camera (pvpython) or isometric (PyVista) |
| Multiple OpenFOAMReader proxies with `--data` | Patch the first one found, log a warning |

---

## Testing

`tests/test_pvsm.py` covers:

1. **PVSM XML parsing** — given `example_state.pvsm`, verify: scalar name is `"Vm"` at `elements[4]`, field association is `'point'` (elements[3] == "1"), `vmin`/`vmax` extracted from `RGBPoints`, `NameOfLastPresetApplied` is empty (triggering `RGBPoints` fallback path)
2. **`pvsm_render.py` CLI parsing** — all flags parse correctly including `time="last"`, `time="mid"`, and float
3. **End-to-end smoke test** *(requires pvpython, marked skipif)*: run `pvsm_render.py` against `example_state.pvsm`, verify `.vtu` exists, `pyvista.read(vtu).n_points > 0`, and `.png` size >= 100KB
4. **`generate_html_from_vtu()`** — loads the `.vtu` from test 3, verify `.html` produced and contains `"renderWindow"` (vtk.js marker)
5. **Cache invalidation** — touching PVSM triggers regeneration; touching unrelated file does not; touching `pvsm_render.py` triggers regeneration
6. **`time="last"` / `time="mid"` dispatch** — unit test the time-value-to-pvpython-call mapping without running pvpython
