# Chamfered Cube Orientation Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 28×28 axis-line SVG + preset popup with a 72×72 chamfered-cube widget that tracks camera orientation, renders 14 clickable regions via `_drawCube()`, and snaps the camera on click.

**Architecture:** All changes are inside `_controls_strip_snippet` in `_extensions/4dpaper/4dpaper.py`. Task 1 writes the failing test suite (TDD); Task 2 makes them pass by implementing the cube geometry, `_drawCube()`, the updated `csSetView_`, and removing the now-dead popup/rotation-mode code.

**Tech Stack:** Python (f-string snippet generation), JavaScript (emitted inline), pytest

---

## File Map

| File | Action |
|---|---|
| `tests/test_controls_strip.py` | Remove 8 tests, update 2, add 11 new |
| `_extensions/4dpaper/4dpaper.py` | Modify `_controls_strip_snippet` |

---

### Task 1: Update test suite (failing state)

**Files:**
- Modify: `tests/test_controls_strip.py`

#### Step 1.1 — Remove 8 obsolete tests

- [ ] **Delete the following test methods** from `tests/test_controls_strip.py`:
  - `TestControlsStripHtml::test_axes_popup_above_corner`
  - `TestControlsStripJs::test_interactor_enabled_on_open`
  - `TestControlsStripJs::test_null_interactor_safe`
  - `TestControlsStripJs::test_click_handler_on_svg`
  - `TestControlsStripJs::test_preset_closes_popup`
  - `TestControlsStripJs::test_corner_cube_checks_locked_flag`
  - `TestControlsStripJs::test_corner_cube_no_locked_gate_when_lock_hidden`
  - `TestControlsStripOrientationLogic::test_preset_buttons_call_set_view`

#### Step 1.2 — Update `test_popup_panels_present_for_active_features`

- [ ] **Replace** the existing `test_popup_panels_present_for_active_features` body with:

```python
def test_popup_panels_present_for_active_features(self):
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True, show_orientation=True)
    # axes popup gone — must be absent
    assert 'id="cs-pop-axes-fig_vm"' not in html
    # lock popup still gone
    assert 'id="cs-pop-lock-fig_vm"' not in html
    # corner cube div must be present
    assert 'id="cs-corner-fig_vm"' in html
```

#### Step 1.3 — Update `test_corner_cube_present_when_show_orientation`

- [ ] **Replace** the existing body with (assert 72×72 size only — style position is verified by `test_cube_svg_size`):

```python
def test_corner_cube_present_when_show_orientation(self):
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
    assert 'id="cs-svg-axes-fig_vm"' in html
    assert 'width="72"' in html
    assert 'height="72"' in html
```

#### Step 1.4 — Add new HTML tests

- [ ] **Add** to `TestControlsStripHtml`:

```python
def test_cube_svg_size(self):
    """SVG corner div is positioned fixed at bottom-left when show_orientation=True."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
    corner_pos = html.find('id="cs-corner-fig_vm"')
    assert corner_pos != -1, "cs-corner div not found"
    region = html[corner_pos:corner_pos + 200]
    assert "bottom:4px" in region
    assert "left:4px" in region

def test_axes_popup_absent(self):
    """cs-pop-axes- must NOT be emitted when show_orientation=True."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
    assert 'id="cs-pop-axes-fig_vm"' not in html
```

#### Step 1.5 — Add new JS tests

- [ ] **Add** to `TestControlsStripJs`:

```python
def test_draw_cube_function_present(self):
    """`_drawCube` emitted when show_orientation=True."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
    assert "_drawCube" in html

def test_draw_cube_absent_when_orientation_hidden(self):
    """`_drawCube` NOT emitted when show_orientation=False."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
    assert "_drawCube" not in html

def test_cs_setview_accepts_direction_array(self):
    """`csSetView_` body normalises direction via `_n3(dir)`."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
    js = html.split("<script>", 1)[1] if "<script>" in html else html
    start = js.find("csSetView_fig_vm")
    assert start != -1, "csSetView_ not found"
    func_body = js[start:start + 600]
    assert "_n3(dir)" in func_body, "_n3(dir) not in csSetView_ body"

def test_interactor_enabled_on_setview(self):
    """`if(_iact)` guard and `setEnabled(1)` both inside csSetView_."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
    js = html.split("<script>", 1)[1] if "<script>" in html else html
    start = js.find("csSetView_fig_vm")
    assert start != -1, "csSetView_ not found"
    func_body = js[start:start + 600]
    assert "if(_iact)" in func_body, "if(_iact) guard missing in csSetView_"
    assert "setEnabled(1)" in func_body, "setEnabled(1) missing in csSetView_"

def test_open_rotation_absent(self):
    """`_openRotation` must NOT appear anywhere in the snippet."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
    assert "_openRotation" not in html

def test_close_rotation_absent(self):
    """`_closeRotation` must NOT appear anywhere in the snippet."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
    assert "_closeRotation" not in html

def test_close_on_toggle_absent(self):
    """`_close_on_toggle` interactor-gate logic must not be emitted.
    Detects: cs-pop-axes- referenced in JS (used to gate interactor on toggle)."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
    js = html.split("<script>", 1)[1] if "<script>" in html else html
    assert "cs-pop-axes-" not in js, \
        "cs-pop-axes- found in JS — _close_on_toggle still emitted"

def test_cube_lock_gate_in_draw_cube(self):
    """`_showLockedBadge` present inside `_drawCube` when show_lock_btn=True."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=True)
    js = html.split("<script>", 1)[1] if "<script>" in html else html
    cube_start = js.find("_drawCube")
    assert cube_start != -1, "_drawCube not found"
    cube_body = js[cube_start:cube_start + 2000]
    assert "_showLockedBadge" in cube_body, \
        "_showLockedBadge not found inside _drawCube with show_lock_btn=True"

def test_cube_no_lock_gate_when_lock_hidden(self):
    """`_showLockedBadge` NOT present inside `_drawCube` when show_lock_btn=False."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=False)
    js = html.split("<script>", 1)[1] if "<script>" in html else html
    cube_start = js.find("_drawCube")
    assert cube_start != -1, "_drawCube not found"
    cube_body = js[cube_start:cube_start + 2000]
    assert "_showLockedBadge" not in cube_body, \
        "_showLockedBadge found inside _drawCube with show_lock_btn=False"
```

#### Step 1.6 — Run tests to verify they fail

- [ ] Run: `pytest tests/test_controls_strip.py -v 2>&1 | tail -40`

Expected: Multiple failures matching the new/updated assertions. No unexpected passes.

- [ ] **Commit**

```bash
git add tests/test_controls_strip.py
git commit -m "test: update controls strip tests for chamfered cube widget (failing)"
```

---

### Task 2: Implement chamfered cube in `_controls_strip_snippet`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py`

Read the full `_controls_strip_snippet` function before starting.

#### Step 2.1 — Change SVG/corner div size to 72×72 and remove axes popup

- [ ] In `_controls_strip_snippet`, find the `cs-corner-{fig_id_safe}` div and SVG element. Change:
  - The outer div style to `position:fixed;bottom:4px;left:4px;z-index:9999;`
  - The SVG `width` and `height` attributes from `28` to `72`
  - SVG title to `"Click face for ortho view · click corner for iso view"`
  - Remove all HTML for `cs-pop-axes-{fig_id_safe}` (the axes preset popup div)
  - Remove the `AXES_POP` style constant if it exists

  The SVG body should be empty — `_drawCube()` will populate it via `innerHTML` each rAF frame.

#### Step 2.2 — Remove `_close_on_toggle`, `_openRotation`, `_closeRotation`

- [ ] Remove the `_close_on_toggle` JS fragment (the block emitted under `show_orientation=True` that references `cs-pop-axes-` to gate the interactor on panel toggle).
- [ ] Remove the `_openRotation()` JS function definition.
- [ ] Remove the `_closeRotation()` JS function definition.
- [ ] Remove any `_openRotation()` / `_closeRotation()` call sites (SVG click listener, `csSetView_` body, etc.).

#### Step 2.3 — Add `_FACES` and `_CORNERS` JS geometry constants

- [ ] Inject the following JS block (as a Python string inside the snippet), emitted only when `show_orientation=True`, placed immediately before the `_drawCube` function definition:

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
```

#### Step 2.4 — Add `_drawCube()` function (replaces `_drawAxes()`)

- [ ] Remove the `_drawAxes()` JS function.

- [ ] In Python, compute `_cube_lock_gate` once before building the `_drawCube` string. The existing code already has a `_cube_lock_gate` variable — update it to use `_showLockedBadge()` (no fig_id suffix):

```python
_cube_lock_gate = (
    f'if(_locked){{_showLockedBadge();return;}}'
) if show_lock_btn else ''
```

- [ ] Emit the `_drawCube` function as a Python f-string. The critical rule for `onclick`: **do not use `var dirStr` or `JSON.stringify`**. Instead, read `p.dir` array elements directly inline in the onclick attribute value. The `_cube_lock_gate` and function name are baked in at Python render time via f-string; `p.dir[0]`, `p.dir[1]`, `p.dir[2]` are evaluated at JS runtime. The resulting generated JS (for `fig_id_safe='fig_vm'`, `show_lock_btn=True`) must look like:

```js
function _drawCube() {
    if (!_renderer || !_svg) return;
    var cam = _renderer.getActiveCamera();
    var pos = cam.getPosition(), fp = cam.getFocalPoint(), vup = cam.getViewUp();
    var vd = _n3([fp[0]-pos[0], fp[1]-pos[1], fp[2]-pos[2]]);
    var right = _n3(_cr(vd, vup));
    var up = _cr(right, vd);
    var cx = 36, cy = 36, R = 28;
    function proj(v) {
        return [cx + R*_dt(v,right), cy - R*_dt(v,up)];
    }
    function depth(verts) {
        var d=0;
        for(var i=0;i<verts.length;i++) d+=_dt(verts[i],vd);
        return d/verts.length;
    }
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
    pieces.sort(function(a,b){ return a.depth - b.depth; });
    var html = '';
    pieces.forEach(function(p) {
        var pts = p.verts.map(function(v){ var s=proj(v); return s[0].toFixed(1)+','+s[1].toFixed(1); }).join(' ');
        html += '<polygon points="'+pts+'" fill="'+p.fill+'" stroke="'+p.stroke+'" stroke-width="1.5"'
              + ' style="cursor:pointer;"'
              + ' onclick="if(_locked){_showLockedBadge();return;}csSetView_fig_vm(['+p.dir[0]+','+p.dir[1]+','+p.dir[2]+'])"/>';
    });
    _svg.innerHTML = html;
}
```

The Python f-string that produces this (with `_cube_lock_gate` and `fig_id_safe` substituted):

```python
_js.append(
    f'  function _drawCube(){{\n'
    f'    if (!_renderer || !_svg) return;\n'
    f'    var cam = _renderer.getActiveCamera();\n'
    f'    var pos = cam.getPosition(), fp = cam.getFocalPoint(), vup = cam.getViewUp();\n'
    f'    var vd = _n3([fp[0]-pos[0], fp[1]-pos[1], fp[2]-pos[2]]);\n'
    f'    var right = _n3(_cr(vd, vup));\n'
    f'    var up = _cr(right, vd);\n'
    f'    var cx=36, cy=36, R=28;\n'
    f'    function proj(v){{ return [cx+R*_dt(v,right), cy-R*_dt(v,up)]; }}\n'
    f'    function depth(verts){{ var d=0; for(var i=0;i<verts.length;i++) d+=_dt(verts[i],vd); return d/verts.length; }}\n'
    f'    var pieces=[];\n'
    f'    _FACES.forEach(function(f){{\n'
    f'      if(_dt(f.normal,vd)>0.05)\n'
    f'        pieces.push({{verts:f.verts,fill:f.fill,stroke:f.stroke,dir:f.dir,depth:depth(f.verts)}});\n'
    f'    }});\n'
    f'    _CORNERS.forEach(function(c){{\n'
    f'      if(_dt(c.normal,vd)>0.05)\n'
    f'        pieces.push({{verts:c.verts,fill:"#c8a800",stroke:"#ffe033",dir:c.dir,depth:depth(c.verts)}});\n'
    f'    }});\n'
    f'    pieces.sort(function(a,b){{return a.depth-b.depth;}});\n'
    f'    var html="";\n'
    f'    pieces.forEach(function(p){{\n'
    f'      var pts=p.verts.map(function(v){{var s=proj(v);return s[0].toFixed(1)+","+s[1].toFixed(1);}}).join(" ");\n'
    f'      html+=\'<polygon points="\'+pts+\'" fill="\'+p.fill+\'" stroke="\'+p.stroke+\'" stroke-width="1.5"\'\n'
    f'           +\' style="cursor:pointer;"\'\n'
    f'           +\' onclick="{_cube_lock_gate}csSetView_{fig_id_safe}([\'+p.dir[0]+\',\'+p.dir[1]+\',\'+p.dir[2]+\'])"/>\';\n'
    f'    }});\n'
    f'    _svg.innerHTML=html;\n'
    f'  }}\n'
)
```

Note: `{{` and `}}` in f-strings produce literal `{` and `}` in the output. `_cube_lock_gate` and `{fig_id_safe}` are Python variables substituted at render time.

#### Step 2.5 — Update `_axLoop` to call `_drawCube` instead of `_drawAxes`

- [ ] Find the `_axLoop` rAF function. Replace the `_drawAxes()` call with `_drawCube()`.

#### Step 2.6 — Update `csSetView_` to accept direction array

- [ ] Replace the existing `csSetView_{fig_id_safe}` function with:

```python
_js.append(
    f'  window.csSetView_{fig_id_safe} = function(dir){{\n'
    f'    if (!_renderer) return;\n'
    f'    var cam = _renderer.getActiveCamera();\n'
    f'    var fp = cam.getFocalPoint(), dist = cam.getDistance();\n'
    f'    var pn = _n3(dir);\n'
    f'    var up = (Math.abs(pn[2]) > 0.9) ? [0,1,0] : [0,0,1];\n'
    f'    cam.setPosition(fp[0]+pn[0]*dist, fp[1]+pn[1]*dist, fp[2]+pn[2]*dist);\n'
    f'    cam.setViewUp(up[0], up[1], up[2]);\n'
    f'    cam.setFocalPoint(fp[0], fp[1], fp[2]);\n'
    f'    _renderer.resetCameraClippingRange();\n'
    f'    if (_iact) _iact.setEnabled(1);\n'
    f'    if (window.renderWindow) window.renderWindow.render();\n'
    f'  }};\n'
)
```

The function no longer accepts string keys (`'iso'`, `'+X'`, etc.) — only direction arrays.

#### Step 2.7 — Ensure `_svg` variable is assigned

- [ ] Ensure `var _svg = document.getElementById('cs-svg-axes-{fig_id_safe}');` is present when `show_orientation=True`. It should be inside the `_wR` polling callback (where `_renderer` is first confirmed available) so the SVG element is guaranteed to exist in the DOM at the time of assignment.

#### Step 2.8 — Run tests

- [ ] Run: `pytest tests/test_controls_strip.py -v 2>&1 | tail -60`

Expected: All tests pass. If failures remain, debug before continuing.

#### Step 2.9 — Commit

```bash
git add _extensions/4dpaper/4dpaper.py
git commit -m "feat: chamfered cube orientation widget (72×72, 14 clickable regions)"
```

---

## Completion Checklist

- [ ] All 8 obsolete tests removed
- [ ] 2 tests updated (`test_popup_panels_present_for_active_features`, `test_corner_cube_present_when_show_orientation`)
- [ ] 11 new tests added and passing (2 HTML + 9 JS)
- [ ] `cs-pop-axes-` absent from generated HTML and JS
- [ ] `width="72" height="72"` in generated HTML
- [ ] `_drawCube` in generated JS (`show_orientation=True`)
- [ ] `_openRotation` / `_closeRotation` / `_close_on_toggle` absent
- [ ] `csSetView_` accepts direction array, calls `_n3(dir)`, calls `setEnabled(1)`
- [ ] No `var dirStr` or `JSON.stringify` in `_drawCube` body
- [ ] Lock gate (`_showLockedBadge()`) present in `_drawCube` when `show_lock_btn=True`, absent when False
- [ ] Full pytest suite green
