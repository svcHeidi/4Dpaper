# Chamfered Cube Orientation Widget Design

## Goal

Replace the 28×28 axis-line SVG + preset popup with a 72×72 chamfered-cube orientation widget. The cube tracks camera orientation in real time, shows 14 clickable regions (6 face views + 8 iso corner views), and snaps the camera directly on click — no popup needed.

---

## Single-file change

All changes are inside `_controls_strip_snippet` in `_extensions/4dpaper/4dpaper.py`. No new Python functions, no Lua changes, no new endpoints.

---

## Component 1: HTML structure

### Corner widget size

`cs-corner-{fig_id_safe}` grows from 28×28 to 72×72.

### Axes popup removed

`cs-pop-axes-{fig_id_safe}` is **no longer emitted**. The `AXES_POP` style constant is removed.

### `_close_on_toggle` removed

The `_close_on_toggle` JS fragment (currently emitted when `show_orientation=True`) checks whether `cs-pop-axes-` is visible to enable/disable the interactor on each panel toggle. Since the popup is gone, this element lookup would always return `null` and silently kill the interactor on every field/time panel open. **`_close_on_toggle` is removed entirely.** Interactor state is managed only by `csSetView_` and the lock button.

### Interactor lifecycle

`_iact.setEnabled(0)` remains in the `_wR` renderer-polling block (interactor starts disabled on load — unchanged). `csSetView_` is the only function that re-enables it (via `_iact.setEnabled(1)`). The user enables rotation by clicking a face or corner; free-drag from that position is then available. The lock button disables the interactor again.

`_openRotation()` and `_closeRotation()` are **removed**. There is no separate "rotation mode" toggle — the cube face/corner click is the single interaction point.

---

### SVG element

```html
<div id="cs-corner-{fig_id_safe}"
     style="position:fixed;bottom:4px;left:4px;z-index:9999;">
  <svg id="cs-svg-axes-{fig_id_safe}" width="72" height="72"
       style="background:rgba(10,10,20,0.0);border-radius:4px;
              display:block;cursor:pointer;"
       title="Click face for ortho view · click corner for iso view"></svg>
</div>
```

The SVG starts empty — `_drawCube()` populates its `innerHTML` every rAF frame.

---

## Component 2: Cube projection

### Geometry constants (JS, declared once at snippet scope)

Chamfer amount `c = 0.25` on a unit cube (±1 on each axis).

**6 square faces** — each entry: `{verts: [[x,y,z]×4], normal: [nx,ny,nz], fill, stroke, dir}`

```js
var _FACES = [
  {verts:[[ 0.75, 0.75,1],[ 0.75,-0.75,1],[-0.75,-0.75,1],[-0.75, 0.75,1]],
   normal:[0,0,1],  fill:"#3a3aaa", stroke:"#6666dd", dir:[0,0,1]},
  {verts:[[ 0.75, 0.75,-1],[ 0.75,-0.75,-1],[-0.75,-0.75,-1],[-0.75, 0.75,-1]],
   normal:[0,0,-1], fill:"#222266", stroke:"#4444aa", dir:[0,0,-1]},
  {verts:[[1, 0.75, 0.75],[1,-0.75, 0.75],[1,-0.75,-0.75],[1, 0.75,-0.75]],
   normal:[1,0,0],  fill:"#8a2222", stroke:"#cc5555", dir:[1,0,0]},
  {verts:[[-1, 0.75, 0.75],[-1,-0.75, 0.75],[-1,-0.75,-0.75],[-1, 0.75,-0.75]],
   normal:[-1,0,0], fill:"#441111", stroke:"#883333", dir:[-1,0,0]},
  {verts:[[ 0.75,1, 0.75],[-0.75,1, 0.75],[-0.75,1,-0.75],[ 0.75,1,-0.75]],
   normal:[0,1,0],  fill:"#1e6b1e", stroke:"#44aa44", dir:[0,1,0]},
  {verts:[[ 0.75,-1, 0.75],[-0.75,-1, 0.75],[-0.75,-1,-0.75],[ 0.75,-1,-0.75]],
   normal:[0,-1,0], fill:"#0d3d0d", stroke:"#226622", dir:[0,-1,0]},
];
```

**8 corner triangles** — chamfer vertices are at distance `c=0.25` from each original corner along each edge:

```js
var _CORNERS = [
  {verts:[[ 0.75,1,1],[1, 0.75,1],[1,1, 0.75]], normal:[ 1, 1, 1], dir:[ 1, 1, 1]},
  {verts:[[ 0.75,1,-1],[1, 0.75,-1],[1,1,-0.75]], normal:[ 1, 1,-1], dir:[ 1, 1,-1]},
  {verts:[[ 0.75,-1,1],[1,-0.75,1],[1,-1, 0.75]], normal:[ 1,-1, 1], dir:[ 1,-1, 1]},
  {verts:[[-0.75,1,1],[-1, 0.75,1],[-1,1, 0.75]], normal:[-1, 1, 1], dir:[-1, 1, 1]},
  {verts:[[ 0.75,-1,-1],[1,-0.75,-1],[1,-1,-0.75]], normal:[ 1,-1,-1], dir:[ 1,-1,-1]},
  {verts:[[-0.75,1,-1],[-1, 0.75,-1],[-1,1,-0.75]], normal:[-1, 1,-1], dir:[-1, 1,-1]},
  {verts:[[-0.75,-1,1],[-1,-0.75,1],[-1,-1, 0.75]], normal:[-1,-1, 1], dir:[-1,-1, 1]},
  {verts:[[-0.75,-1,-1],[-1,-0.75,-1],[-1,-1,-0.75]], normal:[-1,-1,-1], dir:[-1,-1,-1]},
];
// Corner fill/stroke (all yellow):
// fill: "#c8a800", stroke: "#ffe033"
```

The 12 edge rectangles are **not drawn** — they appear as thin dark gaps between faces and corners, acting as natural separators.

### `_drawCube()` algorithm

```js
function _drawCube() {
    if (!_renderer || !_svg) return;
    var cam = _renderer.getActiveCamera();
    var pos = cam.getPosition(), fp = cam.getFocalPoint(), vup = cam.getViewUp();
    var vd = _n3([fp[0]-pos[0], fp[1]-pos[1], fp[2]-pos[2]]);   // view direction
    var right = _n3(_cr(vd, vup));
    var up = _cr(right, vd);
    var cx = 36, cy = 36, R = 28;   // SVG centre and scale radius

    // Project 3D point → SVG coords
    function proj(v) {
        return [cx + R*_dt(v,right), cy - R*_dt(v,up)];
    }
    // Centroid depth for painter's sort
    function depth(verts) {
        var d=0;
        for(var i=0;i<verts.length;i++) d+=_dt(verts[i],vd);
        return d/verts.length;
    }

    // Collect visible pieces (facing viewer)
    var pieces = [];
    _FACES.forEach(function(f) {
        if (_dt(f.normal, vd) > 0.05)
            pieces.push({verts:f.verts, fill:f.fill, stroke:f.stroke,
                         dir:f.dir, depth:depth(f.verts)});
    });
    _CORNERS.forEach(function(c) {
        if (_dt(c.normal, vd) > 0.05)
            pieces.push({verts:c.verts, fill:"#c8a800", stroke:"#ffe033",
                         dir:c.dir, depth:depth(c.verts)});
    });

    // Sort back-to-front
    pieces.sort(function(a,b){ return a.depth - b.depth; });

    // Build SVG innerHTML
    var html = '';
    pieces.forEach(function(p) {
        var pts = p.verts.map(function(v){ var s=proj(v); return s[0].toFixed(1)+','+s[1].toFixed(1); }).join(' ');
        var dirStr = JSON.stringify(p.dir);
        html += '<polygon points="'+pts+'" fill="'+p.fill+'" stroke="'+p.stroke+'" stroke-width="1.5"'
              + ' style="cursor:pointer;"'
              + ' onclick="csSetView_{fig_id_safe}('+dirStr+')"/>';
    });
    _svg.innerHTML = html;
}
```

`_axLoop` calls `_drawCube()` instead of `_drawAxes()`.

---

## Component 3: `csSetView_` — 14 directions

`csSetView_` is extended to accept a direction array `[dx,dy,dz]` (instead of a string key). It normalises the direction, positions the camera, enables the interactor, and renders:

```js
window.csSetView_{fig_id_safe} = function(dir) {
    if (!_renderer) return;
    var cam = _renderer.getActiveCamera();
    var fp = cam.getFocalPoint(), dist = cam.getDistance();
    var pn = _n3(dir);
    // Choose viewUp: use [0,0,1] unless dir is nearly parallel to Z
    var up = (Math.abs(pn[2]) > 0.9) ? [0,1,0] : [0,0,1];
    cam.setPosition(fp[0]+pn[0]*dist, fp[1]+pn[1]*dist, fp[2]+pn[2]*dist);
    cam.setViewUp(up[0], up[1], up[2]);
    cam.setFocalPoint(fp[0], fp[1], fp[2]);
    _renderer.resetCameraClippingRange();
    if (_iact) _iact.setEnabled(1);   // enable interactor after snap
    if (window.renderWindow) window.renderWindow.render();
};
```

**Removed:** `_openRotation()`, `_closeRotation()`. The interactor is enabled on every `csSetView_` call. Locking is handled exclusively by the lock button.

---

## Component 4: Lock gate on cube clicks

When `show_lock_btn=True`, the `_drawCube()` polygon `onclick` is guarded. In Python, the onclick attribute string is built as:

```python
# _lock_gate_js is computed once before the _drawCube function string:
_lock_gate_js = (
    f'if(_locked){{_showLockedBadge();return;}}'
) if show_lock_btn else ''

# Inside _drawCube, the onclick per polygon is (note closing " for HTML attribute):
f' onclick="{_lock_gate_js}csSetView_{fig_id_safe}('+dir_str+')"'
```

Where `dirStr` is a JS `JSON.stringify`-equivalent string like `[1,1,1]` produced by Python string formatting of the direction array. For example for dir `[1,1,1]`:

```python
dir_str = '[' + ','.join(str(d) for d in piece['dir']) + ']'
# onclick="csSetView_fig_vm([1,1,1])"   (no lock gate)
# onclick="if(_locked){_showLockedBadge();return;}csSetView_fig_vm([1,1,1])"   (with lock gate)
```

When `show_lock_btn=False`, `_lock_gate_js` is an empty string — no guard emitted.

---

## Interaction summary

| Action | Result |
|---|---|
| Click face (+Z/−Z/+X/−X/+Y/−Y) | Snap to orthographic view, interactor enabled |
| Click corner (any of 8) | Snap to iso view, interactor enabled |
| Lock button clicked (locked) | All cube clicks blocked, "locked" badge flashes |
| Drag on figure | Rotate freely (interactor must be enabled) |

---

## Testing

All tests in `tests/test_controls_strip.py`.

### Tests to remove

- `test_axes_popup_above_corner` — popup gone (replaced by `test_axes_popup_absent`)
- `test_interactor_enabled_on_open` — `_openRotation` gone
- `test_null_interactor_safe` — `_openRotation`/`_closeRotation` gone
- `test_preset_closes_popup` — `_closeRotation()` no longer in `csSetView_`
- `test_click_handler_on_svg` — SVG-level click handler gone (per-polygon onclick instead)
- `test_preset_buttons_call_set_view` — buttons are now JS-generated polygons, not static HTML
- `test_corner_cube_checks_locked_flag` — SVG addEventListener gone; replaced by `test_cube_lock_gate_in_draw_cube`
- `test_corner_cube_no_locked_gate_when_lock_hidden` — SVG addEventListener gone; replaced by `test_cube_no_lock_gate_when_lock_hidden`

### Tests to update

- `test_corner_cube_present_when_show_orientation` — assert `width="72"` not `width="28"`
- `test_popup_panels_present_for_active_features` — remove assertion for `cs-pop-axes-fig_vm` (popup gone); add assertion that `cs-pop-axes-fig_vm` is absent; keep the existing assertion that `cs-pop-lock-fig_vm` is absent; add a positive assertion that `cs-corner-fig_vm` is present (the corner div must still be emitted)

### Tests that need no change

- `test_interactor_disabled_on_load` — `setEnabled(0)` remains in `_wR` polling block; test passes unchanged

### New tests — `TestControlsStripHtml`

- `test_cube_svg_size` — `width="72" height="72"` in snippet when `show_orientation=True`
- `test_axes_popup_absent` — `cs-pop-axes-` NOT in snippet when `show_orientation=True`

### New tests — `TestControlsStripJs`

- `test_draw_cube_function_present` — `_drawCube` in snippet when `show_orientation=True`
- `test_draw_cube_absent_when_orientation_hidden` — `_drawCube` NOT in snippet when `show_orientation=False`; `test_axes_raf_loop_absent_when_hidden` continues to cover `_axLoop` absence unchanged
- `test_cs_setview_accepts_direction_array` — `csSetView_` function body contains `_n3(dir)` (direction normalisation from array argument)
- `test_interactor_enabled_on_setview` — `if(_iact)` guard and `setEnabled(1)` both present inside `csSetView_` function body
- `test_open_rotation_absent` — `_openRotation` NOT in snippet
- `test_close_rotation_absent` — `_closeRotation` NOT in snippet
- `test_close_on_toggle_absent` — `_close_on_toggle` string (i.e. `cs-pop-axes-` inside a JS interactor-enable check) NOT in snippet
- `test_cube_lock_gate_in_draw_cube` — when `show_lock_btn=True`: `_showLockedBadge` present inside `_drawCube` function body
- `test_cube_no_lock_gate_when_lock_hidden` — when `show_lock_btn=False`: `_showLockedBadge` NOT present inside `_drawCube` function body

---

## What does NOT change

- `generate_html_figure` call signature
- `show_orientation` parameter semantics
- `_iact` declaration and `setEnabled(0)` in the `_wR` renderer-polling block (interactor starts disabled on load)
- `_n3`, `_cr`, `_dt` math helpers
- `_axLoop` requestAnimationFrame loop (calls `_drawCube` instead of `_drawAxes` — same loop, new function)
- Camera sync logic (`_sendCam`, mouseup/touchend listeners)
- Lock widget and badge (`cs-lock-widget-`, `cs-lock-badge-`, `_setLocked`, `_showLockedBadge`)
- Field switcher and time scrubber
