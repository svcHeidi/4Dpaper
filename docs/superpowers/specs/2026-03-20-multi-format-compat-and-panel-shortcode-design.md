# Multi-Format Compatibility + `4d-panel` Shortcode Design

**Date:** 2026-03-20
**Status:** Approved
**Files:** `_extensions/4dpaper/4dpaper.py`, `_extensions/4dpaper/shortcodes.lua`

---

## Goal

Two deliverables in one spec — they share the same files and are naturally sequential:

1. **Format compatibility verification**: confirm `{{< 4d-image >}}` works end-to-end for all formats added by the multi-format loader (STL, VTP, OBJ, PLY, MSH, XDMF, etc.), not just OpenFOAM `.foam`.
2. **`{{< 4d-panel >}}` shortcode**: compose multiple 3D figures into a CSS grid layout (e.g. 2×2, 3×1) as a single self-contained HTML/PNG — machine-friendly syntax, identical embedding model to `4d-image`.

---

## Part 1: Format Compatibility

### Current state

`generate_html_figure()` and `generate_png_figure()` both call `SimulationData(str(src_path)).load()`, which now auto-detects and loads all supported formats. The code already handles empty `field` gracefully:

- `generate_png_figure()`: `if field and (field in surface.point_data ...)` → geometry-only render if field absent or not found.
- `generate_html_figure()`: same conditional guard before adding scalar coloring.

So compatibility is **theoretically complete** for any format that produces a PyVista mesh with at least one time step and non-zero points.

### Verification task

Add a `## Test Figures` section to `analysis_report.qmd` with one `{{< 4d-image >}}` shortcode per new format, using real sample files from `tests/data/`. All files below are confirmed present.

```
{{< 4d-image src="tests/data/base.stl"               field=""       id="fig-test-stl"  caption="STL: base" >}}
{{< 4d-image src="tests/data/airplane.ply"            field=""       id="fig-test-ply"  caption="PLY: airplane" >}}
{{< 4d-image src="tests/data/sphere.obj"              field=""       id="fig-test-obj"  caption="OBJ: sphere" >}}
{{< 4d-image src="tests/data/track0.vtp"              field=""       id="fig-test-vtp"  caption="VTP: track" >}}
{{< 4d-image src="tests/data/slab_cubic.msh"          field=""       id="fig-test-msh"  caption="MSH: slab" >}}
{{< 4d-image src="tests/data/fiber_directions.xdmf"   field="fiber"  id="fig-test-xdmf" caption="XDMF: fibers" >}}
```

Run `quarto render analysis_report.qmd --to html` and confirm all six figures generate without error. Remove the section after verification (or keep as a demo — user's choice).

### What is NOT changing

No code changes needed for format compatibility — it is already handled by `SimulationData`. The verification is purely a render test.

---

## Part 2: `4d-panel` Shortcode

### Layout convention

`layout="COLSxROWS"` — **columns first, then rows**. Examples:

| Value  | Grid shape       |
|--------|-----------------|
| `"2x2"` | 2 columns, 2 rows |
| `"3x1"` | 3 columns, 1 row  |
| `"1x3"` | 1 column, 3 rows  |
| `"2x3"` | 2 columns, 3 rows |

This is **not** standard mathematical row×col notation. It is chosen because columns-first maps directly to `grid-template-columns` and is the natural mental model for "how many across, how many down". This convention must be stated in the shortcode docstring and user-facing documentation.

### Shortcode syntax

```
{{< 4d-panel id="panel-1" layout="2x2" height="800px" caption="Figure 1."
    src1="case.foam"                   id1="fig-vm"   field1="Vm"
    src2="case.foam"                   id2="fig-at"   field2="activationTime"
    src3="tests/data/base.stl"         id3="fig-stl"  field3=""
    src4="tests/data/fiber_directions.xdmf" id4="fig-fib" field4="fiber" >}}
```

**Required attributes:**
- `id` — panel identifier; output files are `state/figures/<id>.html` and `state/figures/<id>.png`
- `layout` — `"COLSxROWS"` string (see table above)
- `src1`, `id1` — at least one sub-figure

**Optional attributes:**
- `height` — total iframe height (default `"800px"`)
- `caption` — figure caption
- `field<n>` — scalar field name for sub-figure n (default `""`)
- `time<n>` — time spec for sub-figure n: `"first"`, `"last"`, `"mid"`, or integer index (default `"mid"`)

**Sub-figure numbering:** `src1`/`id1`/`field1`/`time1` through `srcN`/`idN`/`fieldN`/`timeN`. The parser reads until it finds no `src<n>` for the next n.

### Architecture

Same embedding model as `4d-image`: Python generates one composite file → Lua embeds it as one iframe.

```
4d-panel shortcode
       │
       ▼
parse_panel_shortcodes()          # new: parses flat numbered params
       │
       ▼ (for each sub-figure i)
generate_html_figure(src_i, ...)  # existing: writes state/figures/<id_i>.html
generate_png_figure(src_i, ...)   # existing: writes state/figures/<id_i>.png
       │
       ▼
generate_panel_html(panel_spec)   # new: reads sub-figure HTMLs, wraps in CSS grid
generate_panel_png(panel_spec)    # new: reads sub-figure PNGs, composes with PIL
       │
       ▼
state/figures/<panel-id>.html     # one composite file
state/figures/<panel-id>.png      # one composite PNG
       │
       ▼
fourd_panel() in shortcodes.lua   # new handler — same structure as fourd_image
```

### `parse_panel_shortcodes(text: str) -> list[dict]`

New function in `4dpaper.py`. Same regex pattern as `parse_shortcodes()` but targets `{{< 4d-panel ... >}}`. Returns list of panel dicts:

```python
{
    "id": "panel-1",
    "layout": "2x2",         # "COLSxROWS"
    "height": "800px",
    "caption": "",
    "subfigures": [
        {"src": "case.foam", "id": "fig-vm",  "field": "Vm",   "time": "mid"},
        {"src": "case.foam", "id": "fig-at",  "field": "activationTime", "time": "mid"},
        ...
    ]
}
```

The parser increments `n` from 1 until `src<n>` is absent. Panels missing `id` or with zero sub-figures are skipped with a stderr warning.

### `generate_panel_html(panel: dict, figures_dir: Path) -> None`

Steps:

1. Parse `layout="COLSxROWS"` → `ncols`, `nrows`. Raise `ValueError` if format is wrong.
2. For each sub-figure, call `generate_html_figure(src_i, field_i, time_i, figures_dir/<id_i>.html, fig_id=id_i)`.
3. Read each `figures_dir/<id_i>.html` content.
4. Escape content for srcdoc: replace `&` → `&amp;` and `"` → `&quot;` (same as `shortcodes.lua`).
5. Build CSS grid HTML and write to `figures_dir/<panel-id>.html`:

```html
<div style="display:grid;grid-template-columns:repeat({ncols},1fr);gap:4px;
            width:100%;height:{height};background:#111;">
  <iframe srcdoc="{escaped_html_1}" style="width:100%;height:100%;border:none;"></iframe>
  <iframe srcdoc="{escaped_html_2}" style="width:100%;height:100%;border:none;"></iframe>
  ...
</div>
```

**Camera sync — nested iframe fix:** The panel composite HTML is itself embedded as a srcdoc inside the Quarto page iframe (by `fourd_panel` in Lua). This creates a two-level iframe nesting:

```
Quarto page (has relay listener)
  └─ panel srcdoc iframe  (composite HTML — no relay)
       └─ sub-figure srcdoc iframe  (vtk.js + camera-sync JS)
```

The camera-sync JS in each sub-figure iframe calls `parent.postMessage(...)`, which reaches only the composite HTML, not the Quarto relay. The fix: `generate_panel_html()` must inject a re-relay script into the composite HTML that forwards `4dpaper-camera` and `4dpaper-field-update` messages from child iframes to `top`:

```html
<script>
window.addEventListener("message", function(e) {
  if (!e.data) return;
  if (e.data.type === "4dpaper-camera" || e.data.type === "4dpaper-field-update") {
    top.postMessage(e.data, "*");
  }
});
</script>
```

This script is **bidirectional** — it must forward messages both up and down:

```html
<script>
window.addEventListener("message", function(e) {
  if (!e.data) return;
  // Upward: camera/field messages from children → top (Quarto relay)
  if (e.data.type === "4dpaper-camera" || e.data.type === "4dpaper-field-update") {
    top.postMessage(e.data, "*");
  }
  // Downward: acks from top → broadcast to all child iframes
  if (e.data.type === "4dpaper-camera-ack" || e.data.type === "4dpaper-field-ack") {
    var iframes = document.querySelectorAll("iframe");
    for (var i = 0; i < iframes.length; i++) {
      iframes[i].contentWindow.postMessage(e.data, "*");
    }
  }
});
</script>
```

**Why bidirectional:** When the Quarto relay calls `e.source.postMessage(ack, "*")` on success, `e.source` is the composite iframe (it was the sender of `top.postMessage`). Without the downward leg, the ack never reaches the sub-figure and the green "📷 Camera synced" badge never appears. Broadcasting acks to all children is safe — each sub-figure's ack listener filters by `e.data.fig_id === FIG_ID` (baked in at generation time), so only the rotating sub-figure reacts. No infinite loop: camera messages travel children → composite → top; acks travel top → composite → children — opposite directions, different types.

This script is inserted once into the composite HTML (before the grid div). The Quarto relay at `top` receives camera messages and calls `fetch("/camera/...")` as normal.

### `generate_panel_png(panel: dict, figures_dir: Path) -> None`

Steps:

1. Parse `layout="COLSxROWS"` → `ncols`, `nrows`.
2. For each sub-figure, call `generate_png_figure(src_i, field_i, time_i, figures_dir/<id_i>.png, fig_id=id_i)`.
3. Load each PNG with `PIL.Image.open()`.
4. Compute cell size: `cell_w = 1920 // ncols`, `cell_h = 1080 // nrows`.
5. Resize each image to `(cell_w, cell_h)`.
6. Paste into a `(1920, 1080)` canvas in row-major order (left-to-right, then top-to-bottom).
7. Save to `figures_dir/<panel-id>.png`.

PIL (Pillow 12.1.1) is already available in the venv.

### Cache invalidation

The composite panel HTML/PNG are regenerated if the composite file does not exist **or** if its `mtime` is older than any of:
- Any sub-figure source file (`src_i`)
- Any sub-figure camera JSON (`state/camera_<id_i>.json`)
- `4dpaper.py` itself (existing `script_newer` logic)

Implementation: after generating all sub-figures, check `composite_mtime < max(subfig_mtime for each id_i)`. Use `Path.stat().st_mtime`. If the composite is stale, regenerate it. Do not reuse `is_cache_valid()` for this check — implement a direct mtime comparison against the composite path.

### `fourd_panel` in `shortcodes.lua`

Same structure as `fourd_image`, with these differences:
- Height is read from `kwargs["height"]` (default `"800px"`). `fourd_image` hardcodes `600px` and does not accept a height kwarg — `fourd_panel` does.
- The iframe `height` attribute uses the `height` kwarg value.
- Placeholder text says "4D Panel" instead of "4D Figure".

The `_relay_injected` guard is shared — `fourd_panel` uses the same guard. If `fourd_panel` is the first figure on the page, it injects the relay script; otherwise it skips it (same as `fourd_image`).

**Registration:** Add `["4d-panel"] = fourd_panel` to the return table in `shortcodes.lua`:

```lua
return {
  ["4d-image"] = fourd_image,
  ["4d-video"] = fourd_video,
  ["4d-panel"] = fourd_panel,
}
```

### Main dispatch (`__main__` section of `4dpaper.py`)

The existing loop over QMD files uses `qmd_files` and `qmd` as variable names (matching the current code). Add panel parsing inside the same loop, then process panels after figures:

```python
panels = []
for qmd in qmd_files:
    text = qmd.read_text()
    figures.extend(parse_shortcodes(text))
    videos.extend(parse_video_shortcodes(text))
    panels.extend(parse_panel_shortcodes(text))

# ... existing figures loop ...
# ... existing videos loop ...

for panel in panels:
    generate_panel_html(panel, figures_dir)
    generate_panel_png(panel, figures_dir)
```

---

## What is NOT changing

- `SimulationData`, `data_loader.py` — no changes.
- `generate_html_figure()`, `generate_png_figure()` — called unchanged.
- `fourd_image`, `fourd_video` Lua handlers — no changes.
- Camera sync relay script in `shortcodes.lua` — no changes (re-relay is in composite HTML, not Lua).
- `parse_shortcodes()`, `parse_video_shortcodes()` — no changes.

---

## Error handling

- Missing `id` or zero sub-figures: skip panel with `print(..., file=sys.stderr)` warning.
- Sub-figure generation failure: propagate existing `sys.exit(1)` behavior.
- `layout` not in `"COLSxROWS"` format: raise `ValueError` with message explaining expected format.
- Number of sub-figures < ncols × nrows: allowed — missing cells render as blank black tiles (empty grid cells).
