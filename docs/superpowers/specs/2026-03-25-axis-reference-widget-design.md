# Axis Reference Widget Design

## Overview

Replace the chamfered cube orientation widget with a lighter, cleaner widget consisting of:
1. A rotating XYZ axis reference frame — clicking axis arrows snaps to ortho views
2. A single `iso ↻` cycle button — each click advances through the 4 upper iso views

This replaces all chamfered-cube code (`_drawCube`, `_FACES`, `_CORNERS`) while keeping the same surrounding infrastructure: `_axLoop` animation frame, event delegation pattern, lock gate (`_locked`, `_showLockedBadge`), `csSetView_<fig_id>`, `_n3`/`_cr`/`_dt` helpers.

---

## Widget Layout

The existing `cs-corner-<fig_id>` div currently wraps only the SVG (`position:fixed;bottom:4px;left:4px;z-index:9999`). **Change it** to a flex row that also holds the iso button and flash span:

```html
<div id="cs-corner-{fig_id_safe}"
     style="position:fixed;bottom:4px;left:4px;z-index:9999;display:flex;align-items:center;gap:6px;">
  <svg id="cs-svg-axes-{fig_id_safe}" width="56" height="56" viewBox="-1.1 -1.1 2.2 2.2"
       style="display:block;cursor:pointer;"></svg>
  <!-- iso button and flash span: only rendered when show_orientation=True -->
  <button id="cs-btn-iso-{fig_id_safe}" ...>iso ↻</button>
  <span id="cs-iso-flash-{fig_id_safe}"
        style="font-size:9px;color:#ffe033;font-family:monospace;min-width:60px;"></span>
</div>
```

The SVG, button, and flash span are siblings inside the flex container. All three are rendered only when `show_orientation=True`; the whole corner div is omitted when `show_orientation=False`.

---

## Rotating XYZ Reference (SVG)

**Size:** 56×56 px, `viewBox="-1.1 -1.1 2.2 2.2"` (coordinate space: origin at center, axes extend to ±1).

**Axes and colors:**
| Axis | Line/arrowhead color | Label color | World direction |
|------|---------------------|-------------|-----------------|
| Z | `#6699ff` | `#99aaff` | (0,0,1) — up |
| X | `#ff6666` | `#ff9999` | (1,0,0) — right |
| Y | `#66cc66` | `#99cc99` | (0,1,0) — lower-left |

Each axis:
- A `<line>` from origin (0,0) to projected tip (cx, cy)
- An arrowhead `<polygon>` at the tip; fill = same color as line
- A `<text>` label (X/Y/Z) near the tip; fill = label color
- A `<circle>` at the tail end (opposite the arrowhead, ~r=0.12); stroke = line color, fill = transparent; this is the click target for the negative-direction view

**Camera tracking (called each frame from `_axLoop` — replace `_drawCube()` call with `_drawAxes()`):**
- `function _drawAxes()` replaces `_svg.innerHTML` each frame with freshly projected SVG elements (same pattern as old `_drawCube`). The SVG element starts empty; `_drawAxes` is always the sole writer.
- Projection: use `getViewUp` and `getDirectionOfProjection` to build a view-space basis (same math as old cube draw loop); then for each world axis vector `[1,0,0]`, `[0,1,0]`, `[0,0,1]`, compute the projected 2D point `(cx, cy)` in viewBox coordinates using the `_n3`/`_cr`/`_dt` helpers already present in the snippet.
- No culling needed — all 3 axes always drawn.
- No inline event handlers in the innerHTML — events use delegation (see below).

**Click interaction — `data-dir` format:**

Uses the **numeric comma-separated format** compatible with the existing `dv.split(",").map(Number)` parser:

- Arrowhead polygon + label: `data-dir="1,0,0"` / `"0,1,0"` / `"0,0,1"` (positive ortho)
- Tail circle: `data-dir="-1,0,0"` / `"0,-1,0"` / `"0,0,-1"` (negative ortho)

Single `_svg.addEventListener("click", ...)` registered once inside the `_wR` polling block (after `_svg` is assigned — same location as current cube click listener). The `_wR` block guarantees `_svg` is non-null before registering. Handler:

```js
var dv = e.target.getAttribute("data-dir");
if (!dv) return;
if (_locked) { _showLockedBadge(); return; }   // only emitted when show_lock_btn=True
csSetView_{fig_id_safe}(dv.split(",").map(Number));
```

Lock gate **blocks the camera snap** — returns immediately without calling `csSetView_`.

---

## Iso Cycle Button

**HTML** (inside the flex container, rendered only when `show_orientation=True`):
```html
<button id="cs-btn-iso-{fig_id_safe}"
        style="background:rgba(200,168,0,0.2);border:1px solid #c8a800;border-radius:4px;
               color:#ffe033;font-size:10px;padding:2px 8px;font-family:monospace;cursor:pointer;"
        onclick="...">iso ↻</button>
<span id="cs-iso-flash-{fig_id_safe}"
      style="font-size:9px;color:#ffe033;font-family:monospace;min-width:60px;"></span>
```

**JS constants** (defined near the top of the controls JS block, before `_wR`):
```js
var _ISO_VIEWS = [[1,1,1],[-1,1,1],[-1,-1,1],[1,-1,1]];
var _ISO_NAMES = ["+X+Y+Z","-X+Y+Z","-X-Y+Z","+X-Y+Z"];
var _isoIdx = 0;
var _isoT;
```

**onclick handler** (inline on the button — the button element is static, no rAF churn):
```js
if(_locked){_showLockedBadge();return;}
csSetView_{fig_id_safe}(_ISO_VIEWS[_isoIdx]);
var fl=document.getElementById('cs-iso-flash-{fig_id_safe}');
if(fl){fl.textContent=_ISO_NAMES[_isoIdx];clearTimeout(_isoT);_isoT=setTimeout(function(){fl.textContent='';},1400);}
_isoIdx=(_isoIdx+1)%4;
```

Order of operations per click:
1. Lock check first — if locked, show badge and return (no snap, no index advance)
2. Snap to `_ISO_VIEWS[_isoIdx]`
3. Flash `_ISO_NAMES[_isoIdx]` for 1.4 s (instant clear at 1.4 s, no fade animation)
4. Advance `_isoIdx`

`_isoIdx` is transient JS state — resets to 0 on page reload.

---

## Removed Code

**Deleted entirely from `_controls_strip_snippet`:**
- `_FACES` constant (6 cube face definitions)
- `_CORNERS` constant (8 cube corner positions)
- `_drawCube()` function

**Existing tests to remove** (they assert the presence of deleted code):
- `test_draw_cube_function_present` — asserts `_drawCube` present
- `test_draw_cube_absent_when_orientation_hidden` — asserts `_drawCube` absent conditionally
- `test_cube_lock_gate_in_draw_cube` — asserts lock gate in `_drawCube`
- `test_cube_no_lock_gate_when_lock_hidden` — asserts no lock gate in `_drawCube`

**Existing test to rename** (still valid but misleading name):
- `test_corner_cube_present_when_show_orientation` → rename to `test_axis_widget_svg_present_when_show_orientation`; keep the assertion (`width="56"` / `height="56"`)

**Unchanged:**
- `_axLoop` (now calls `_drawAxes()` instead of `_drawCube()`)
- `csSetView_<fig_id>` (unchanged API — still accepts `[x,y,z]` direction array)
- `_n3`, `_cr`, `_dt` helpers
- Lock infrastructure (`_locked`, `_showLockedBadge`, `_iact.setEnabled`)
- `_wR` polling block structure

---

## Testing

**Tests to delete:**
- `test_draw_cube_function_present`
- `test_draw_cube_absent_when_orientation_hidden`
- `test_cube_lock_gate_in_draw_cube`
- `test_cube_no_lock_gate_when_lock_hidden`

**Test to rename:**
- `test_corner_cube_present_when_show_orientation` → `test_axis_widget_svg_present_when_show_orientation` (assertion unchanged: `width="56"` / `height="56"`)

All other existing tests must continue passing.

**New tests to add:**

- `test_drawaxes_function_present` — asserts `function _drawAxes(` in output when `show_orientation=True` (named function declaration, not var assignment); asserts `_drawCube` NOT in output.

- `test_axis_reference_absent_when_orientation_hidden` — `show_orientation=False`: asserts `_drawAxes` not in output; asserts `iso ↻` not in output.

- `test_axis_click_delegation` — asserts `_svg.addEventListener("click"` in output; asserts `data-dir` appears in `_drawAxes` function body; asserts `dv.split(",").map(Number)` in the click listener.

- `test_axis_positive_directions` — asserts `data-dir="1,0,0"`, `data-dir="0,1,0"`, `data-dir="0,0,1"` appear in `_drawAxes` function body.

- `test_axis_negative_directions` — asserts `data-dir="-1,0,0"`, `data-dir="0,-1,0"`, `data-dir="0,0,-1"` appear in `_drawAxes` function body.

- `test_iso_button_present` — asserts `iso ↻` in output; asserts `cs-btn-iso-` in output; asserts `cs-iso-flash-` in output; all when `show_orientation=True`.

- `test_iso_button_absent_when_orientation_hidden` — `show_orientation=False`: asserts `iso ↻` not in output; asserts `cs-btn-iso-` not in output.

- `test_iso_cycle_views` — asserts `_ISO_VIEWS` in output; asserts `[1,1,1]` in output (first entry); asserts `_ISO_NAMES` in output; asserts `_isoIdx` in output.

- `test_iso_lock_gate` — `show_lock_btn=True`: in the iso button onclick, asserts `if(_locked)` appears before `csSetView_` and before `_isoIdx=`.

- `test_iso_no_lock_gate_when_lock_hidden` — `show_lock_btn=False`: asserts iso button onclick does NOT contain `if(_locked)`.
