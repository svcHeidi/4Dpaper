# Axis Reference Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chamfered cube orientation widget with a rotating XYZ axis reference frame + a single `iso ↻` cycle button that steps through 4 upper iso views.

**Architecture:** All changes are in `_controls_strip_snippet` in `4dpaper.py`. The cube constants `_FACES`/`_CORNERS` and `_drawCube()` are removed; a new `_drawAxes()` function draws 3 colored axis arrows + tail circles each rAF frame. An `iso ↻` button is added to the corner widget HTML; its click listener is wired in JS (same pattern as the lock widget). Tests are updated in parallel: 4 old cube tests deleted, 1 renamed, 10 new tests added.

**Tech Stack:** Python f-strings (HTML+JS generation), pytest, vtk.js (in-browser, not tested directly)

---

## File Map

| File | Change |
|------|--------|
| `_extensions/4dpaper/4dpaper.py` | Replace `_FACES`+`_CORNERS`+`_drawCube` with `_drawAxes`; expand corner widget HTML; add iso JS vars + listener |
| `tests/test_controls_strip.py` | Delete 4 cube tests, rename 1 test, add 10 new tests |

---

## Task 1: Update tests (delete old, rename one, add new failing tests)

**Files:**
- Modify: `tests/test_controls_strip.py`

- [ ] **Step 1: Delete the 4 tests that assert on removed code**

In `tests/test_controls_strip.py`, delete these 4 complete test methods:

```
test_draw_cube_function_present          (around line 262)
test_draw_cube_absent_when_orientation_hidden  (around line 268)
test_cube_lock_gate_in_draw_cube         (around line 316)
test_cube_no_lock_gate_when_lock_hidden  (around line 327)
```

- [ ] **Step 2: Rename `test_corner_cube_present_when_show_orientation`**

Find the method at ~line 102:
```python
def test_corner_cube_present_when_show_orientation(self):
```
Rename to:
```python
def test_axis_widget_svg_present_when_show_orientation(self):
```
Keep the assertions unchanged (they check `width="56"` / `height="56"` / `id="cs-svg-axes-fig_vm"` — all still valid).

- [ ] **Step 3: Run existing tests to confirm the remaining tests still pass**

```bash
cd /Users/simaocastro/4Dpapers && python -m pytest tests/test_controls_strip.py -v 2>&1 | tail -20
```

Expected: all remaining tests PASS (the deleted tests are gone, nothing broken yet).

- [ ] **Step 4: Add new failing tests to `TestControlsStripOrientationLogic` class**

Append these tests inside the `TestControlsStripOrientationLogic` class (after the last existing method in that class, around line 403):

```python
    def test_drawaxes_function_present(self):
        """`function _drawAxes(` emitted when show_orientation=True; `_drawCube` NOT emitted."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "function _drawAxes(" in html
        assert "_drawCube" not in html
        assert "_FACES" not in html
        assert "_CORNERS" not in html

    def test_axis_reference_absent_when_orientation_hidden(self):
        """When show_orientation=False: no _drawAxes, no iso button."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert "_drawAxes" not in html
        assert "iso" not in html

    def test_axis_click_delegation(self):
        """SVG click listener uses data-dir and dv.split(',').map(Number)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert '_svg.addEventListener("click"' in html
        # data-dir used inside _drawAxes body
        draw_start = html.find("function _drawAxes(")
        assert draw_start != -1
        draw_body = html[draw_start:draw_start + 1000]
        assert 'data-dir="' in draw_body
        # existing parser still used in click listener
        assert 'dv.split(",").map(Number)' in html

    def test_axis_positive_directions(self):
        """_drawAxes emits data-dir for all 3 positive ortho directions."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        draw_start = html.find("function _drawAxes(")
        assert draw_start != -1
        draw_body = html[draw_start:draw_start + 1000]
        assert 'data-dir="1,0,0"' in draw_body
        assert 'data-dir="0,1,0"' in draw_body
        assert 'data-dir="0,0,1"' in draw_body

    def test_axis_negative_directions(self):
        """_drawAxes emits data-dir for all 3 negative ortho directions (tail circles)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        draw_start = html.find("function _drawAxes(")
        assert draw_start != -1
        draw_body = html[draw_start:draw_start + 1000]
        assert 'data-dir="-1,0,0"' in draw_body
        assert 'data-dir="0,-1,0"' in draw_body
        assert 'data-dir="0,0,-1"' in draw_body

    def test_iso_button_present(self):
        """Iso button, id, and flash span present when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "iso" in html
        assert 'id="cs-btn-iso-fig_vm"' in html
        assert 'id="cs-iso-flash-fig_vm"' in html

    def test_iso_button_absent_when_orientation_hidden(self):
        """Iso button absent when show_orientation=False."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'cs-btn-iso-' not in html
        assert 'cs-iso-flash-' not in html

    def test_iso_cycle_views(self):
        """_ISO_VIEWS with 4 entries, _ISO_NAMES, _isoIdx present when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "_ISO_VIEWS" in html
        assert "[1,1,1]" in html   # first iso view entry
        assert "_ISO_NAMES" in html
        assert "_isoIdx" in html

    def test_iso_lock_gate(self):
        """Iso button listener has lock check before csSetView_ and before _isoIdx= when show_lock_btn=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        btn_pos = js.find('cs-btn-iso-fig_vm')
        assert btn_pos != -1, "iso button listener not found in JS"
        btn_section = js[btn_pos:btn_pos + 400]
        locked_pos = btn_section.find("if(_locked)")
        setview_pos = btn_section.find("csSetView_fig_vm")
        idx_pos = btn_section.find("_isoIdx=")
        assert locked_pos != -1, "if(_locked) not in iso button handler"
        assert locked_pos < setview_pos, "if(_locked) must come before csSetView_"
        assert locked_pos < idx_pos, "if(_locked) must come before _isoIdx="

    def test_iso_no_lock_gate_when_lock_hidden(self):
        """Iso button listener has NO lock check when show_lock_btn=False."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=False)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        btn_pos = js.find('cs-btn-iso-fig_vm')
        assert btn_pos != -1, "iso button listener not found in JS"
        btn_section = js[btn_pos:btn_pos + 400]
        assert "if(_locked)" not in btn_section, \
            "if(_locked) must NOT be in iso button handler when show_lock_btn=False"
```

- [ ] **Step 5: Run tests to confirm new tests FAIL (as expected)**

```bash
cd /Users/simaocastro/4Dpapers && python -m pytest tests/test_controls_strip.py -v -k "drawaxes or axis_click or axis_positive or axis_negative or iso_button or iso_cycle or iso_lock or iso_no_lock or axis_reference_absent" 2>&1 | tail -20
```

Expected: all 10 new tests FAIL (implementation not yet updated).

- [ ] **Step 6: Commit tests**

```bash
cd /Users/simaocastro/4Dpapers && git add tests/test_controls_strip.py && git commit -m "test: update tests for axis reference widget (TDD)"
```

---

## Task 2: Implement axis reference widget in `_controls_strip_snippet`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py:595-863`

### Step 1: Update `corner_widget` HTML (lines 595–605)

- [ ] Replace the current `corner_widget` assignment with the new flex row layout that includes SVG + iso button + flash span.

Find and replace this block (lines 595–605):
```python
    corner_widget = ""
    if show_orientation:
        corner_widget = (
            f'<div id="cs-corner-{fig_id_safe}"'
            f' style="position:fixed;bottom:4px;left:4px;z-index:9999;">\n'
            f'  <svg id="cs-svg-axes-{fig_id_safe}" width="56" height="56"'
            f' style="background:rgba(10,10,20,0.55);border:1px solid rgba(255,255,255,0.12);'
            f'border-radius:4px;display:block;cursor:pointer;"'
            f' title="Click face for ortho view \u00b7 click corner for iso view"></svg>\n'
            f'</div>\n'
        )
```

Replace with:
```python
    corner_widget = ""
    if show_orientation:
        corner_widget = (
            f'<div id="cs-corner-{fig_id_safe}"'
            f' style="position:fixed;bottom:4px;left:4px;z-index:9999;'
            f'display:flex;align-items:center;gap:6px;">\n'
            f'  <svg id="cs-svg-axes-{fig_id_safe}" width="56" height="56"'
            f' style="background:rgba(10,10,20,0.55);border:1px solid rgba(255,255,255,0.12);'
            f'border-radius:4px;display:block;cursor:pointer;"'
            f' title="Click axis tip: ortho view \u00b7 Click axis tail: opposite view"></svg>\n'
            f'  <button id="cs-btn-iso-{fig_id_safe}"'
            f' style="background:rgba(200,168,0,0.2);border:1px solid #c8a800;border-radius:4px;'
            f'color:#ffe033;font-size:10px;padding:2px 8px;font-family:monospace;cursor:pointer;"'
            f' title="Cycle iso views">iso \u21bb</button>\n'
            f'  <span id="cs-iso-flash-{fig_id_safe}"'
            f' style="font-size:9px;color:#ffe033;font-family:monospace;min-width:60px;"></span>\n'
            f'</div>\n'
        )
```

- [ ] **Run tests to check no regressions yet**

```bash
cd /Users/simaocastro/4Dpapers && python -m pytest tests/test_controls_strip.py -v 2>&1 | tail -10
```

Expected: new iso-presence tests now PASS; drawAxes tests still FAIL.

### Step 2: Replace `_FACES` + `_CORNERS` + `_drawCube` + `_axLoop` with `_drawAxes`

- [ ] Find this entire block inside the `if show_orientation:` branch (lines 784–863) and replace it.

**Find** (the whole `_js.append(...)` call from `var _renderer=null` through `csSetView_`):

```python
    if show_orientation:
        _cube_lock_gate = (
            f'if(_locked){{_showLockedBadge();return;}}'
        ) if show_lock_btn else ''
        _js.append(
            f'  var _renderer=null;\n'
            f'  function _n3(v){{var l=Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);'
            f'return l<1e-10?[0,0,1]:[v[0]/l,v[1]/l,v[2]/l];}}\n'
            f'  function _cr(a,b){{return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}}\n'
            f'  function _dt(a,b){{return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}}\n'
            f'  var _FACES=[\n'
            f'    {{verts:[[0.75,0.75,1],[0.75,-0.75,1],[-0.75,-0.75,1],[-0.75,0.75,1]],'
            f'normal:[0,0,1],fill:"#3a3aaa",stroke:"#6666dd",dir:[0,0,1]}},\n'
            f'    {{verts:[[0.75,0.75,-1],[0.75,-0.75,-1],[-0.75,-0.75,-1],[-0.75,0.75,-1]],'
            f'normal:[0,0,-1],fill:"#222266",stroke:"#4444aa",dir:[0,0,-1]}},\n'
            f'    {{verts:[[1,0.75,0.75],[1,-0.75,0.75],[1,-0.75,-0.75],[1,0.75,-0.75]],'
            f'normal:[1,0,0],fill:"#8a2222",stroke:"#cc5555",dir:[1,0,0]}},\n'
            f'    {{verts:[[-1,0.75,0.75],[-1,-0.75,0.75],[-1,-0.75,-0.75],[-1,0.75,-0.75]],'
            f'normal:[-1,0,0],fill:"#441111",stroke:"#883333",dir:[-1,0,0]}},\n'
            f'    {{verts:[[0.75,1,0.75],[-0.75,1,0.75],[-0.75,1,-0.75],[0.75,1,-0.75]],'
            f'normal:[0,1,0],fill:"#1e6b1e",stroke:"#44aa44",dir:[0,1,0]}},\n'
            f'    {{verts:[[0.75,-1,0.75],[-0.75,-1,0.75],[-0.75,-1,-0.75],[0.75,-1,-0.75]],'
            f'normal:[0,-1,0],fill:"#0d3d0d",stroke:"#226622",dir:[0,-1,0]}},\n'
            f'  ];\n'
            f'  var _CORNERS=[\n'
            f'    {{verts:[[0.75,1,1],[1,0.75,1],[1,1,0.75]],normal:[1,1,1],dir:[1,1,1]}},\n'
            f'    {{verts:[[0.75,1,-1],[1,0.75,-1],[1,1,-0.75]],normal:[1,1,-1],dir:[1,1,-1]}},\n'
            f'    {{verts:[[0.75,-1,1],[1,-0.75,1],[1,-1,0.75]],normal:[1,-1,1],dir:[1,-1,1]}},\n'
            f'    {{verts:[[-0.75,1,1],[-1,0.75,1],[-1,1,0.75]],normal:[-1,1,1],dir:[-1,1,1]}},\n'
            f'    {{verts:[[0.75,-1,-1],[1,-0.75,-1],[1,-1,-0.75]],normal:[1,-1,-1],dir:[1,-1,-1]}},\n'
            f'    {{verts:[[-0.75,1,-1],[-1,0.75,-1],[-1,1,-0.75]],normal:[-1,1,-1],dir:[-1,1,-1]}},\n'
            f'    {{verts:[[-0.75,-1,1],[-1,-0.75,1],[-1,-1,0.75]],normal:[-1,-1,1],dir:[-1,-1,1]}},\n'
            f'    {{verts:[[-0.75,-1,-1],[-1,-0.75,-1],[-1,-1,-0.75]],normal:[-1,-1,-1],dir:[-1,-1,-1]}},\n'
            f'  ];\n'
            f'  var _svg=null;\n'
            f'  function _drawCube(){{\n'
            f'    if(!_renderer||!_svg)return;\n'
            f'    var cam=_renderer.getActiveCamera();\n'
            f'    var pos=cam.getPosition(),fp=cam.getFocalPoint(),vup=cam.getViewUp();\n'
            f'    var vd=_n3([fp[0]-pos[0],fp[1]-pos[1],fp[2]-pos[2]]);\n'
            f'    var right=_n3(_cr(vd,vup));\n'
            f'    var up=_cr(right,vd);\n'
            f'    var cx=28,cy=28,R=22;\n'
            f'    function proj(v){{return[cx+R*_dt(v,right),cy-R*_dt(v,up)];}}\n'
            f'    function depth(verts){{var d=0;for(var i=0;i<verts.length;i++)d+=_dt(verts[i],vd);return d/verts.length;}}\n'
            f'    var pieces=[];\n'
            f'    _FACES.forEach(function(f){{\n'
            f'      if(_dt(f.normal,vd)<-0.05)\n'
            f'        pieces.push({{verts:f.verts,fill:f.fill,stroke:f.stroke,dir:f.dir,depth:depth(f.verts)}});\n'
            f'    }});\n'
            f'    _CORNERS.forEach(function(c){{\n'
            f'      if(_dt(c.normal,vd)<-0.05)\n'
            f'        pieces.push({{verts:c.verts,fill:"#c8a800",stroke:"#ffe033",dir:c.dir,depth:depth(c.verts)}});\n'
            f'    }});\n'
            f'    pieces.sort(function(a,b){{return b.depth-a.depth;}});\n'
            f'    var html="";\n'
            f'    pieces.forEach(function(p){{\n'
            f'      var pts=p.verts.map(function(v){{var s=proj(v);return s[0].toFixed(1)+","+s[1].toFixed(1);}}).join(" ");\n'
            f'      html+=\'<polygon points="\'+pts+\'" fill="\'+p.fill+\'" stroke="\'+p.stroke+\'" stroke-width="1.5"\'\n'
            f'           +\' style="cursor:pointer;"\'\n'
            f'           +\' data-dir="\'+p.dir[0]+\',\'+p.dir[1]+\',\'+p.dir[2]+\'"/>\';'
            f'\n'
            f'    }});\n'
            f'    _svg.innerHTML=html;\n'
            f'  }}\n'
            f'  function _axLoop(){{_drawCube();requestAnimationFrame(_axLoop);}}\n'
            f'  window.csSetView_{fig_id_safe}=function(dir){{\n'
            f'    if(!_renderer)return;\n'
            f'    var cam=_renderer.getActiveCamera();\n'
            f'    var fp=cam.getFocalPoint(),dist=cam.getDistance();\n'
            f'    var pn=_n3(dir);\n'
            f'    var up=(Math.abs(pn[2])>0.9)?[0,1,0]:[0,0,1];\n'
            f'    cam.setPosition(fp[0]+pn[0]*dist,fp[1]+pn[1]*dist,fp[2]+pn[2]*dist);\n'
            f'    cam.setViewUp(up[0],up[1],up[2]);\n'
            f'    cam.setFocalPoint(fp[0],fp[1],fp[2]);\n'
            f'    _renderer.resetCameraClippingRange();\n'
            f'    if(_iact)_iact.setEnabled(1);\n'
            f'    if(window.renderWindow)window.renderWindow.render();\n'
            f'  }};\n'
        )
    else:
        _js.append(f'  var _renderer=null;\n')
```

**Replace with** (removes `_FACES`/`_CORNERS`/`_drawCube`, adds `_drawAxes` + iso vars + iso listener):

```python
    if show_orientation:
        _iso_lock_gate = (
            f'      if(_locked){{_showLockedBadge();return;}}\n'
        ) if show_lock_btn else ''
        _js.append(
            f'  var _renderer=null;\n'
            f'  function _n3(v){{var l=Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);'
            f'return l<1e-10?[0,0,1]:[v[0]/l,v[1]/l,v[2]/l];}}\n'
            f'  function _cr(a,b){{return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}}\n'
            f'  function _dt(a,b){{return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}}\n'
            f'  var _svg=null;\n'
            f'  function _drawAxes(){{\n'
            f'    if(!_renderer||!_svg)return;\n'
            f'    var cam=_renderer.getActiveCamera();\n'
            f'    var pos=cam.getPosition(),fp=cam.getFocalPoint(),vup=cam.getViewUp();\n'
            f'    var vd=_n3([fp[0]-pos[0],fp[1]-pos[1],fp[2]-pos[2]]);\n'
            f'    var right=_n3(_cr(vd,vup));\n'
            f'    var up=_cr(right,vd);\n'
            f'    var cx=28,cy=28,R=22;\n'
            f'    function proj(v){{return[cx+R*_dt(v,right),cy-R*_dt(v,up)];}}\n'
            f'    var axes=[\n'
            f'      {{w:[1,0,0],col:"#ff6666",lcol:"#ff9999",lbl:"X",pd:"1,0,0",nd:"-1,0,0"}},\n'
            f'      {{w:[0,1,0],col:"#66cc66",lcol:"#99cc99",lbl:"Y",pd:"0,1,0",nd:"0,-1,0"}},\n'
            f'      {{w:[0,0,1],col:"#6699ff",lcol:"#99aaff",lbl:"Z",pd:"0,0,1",nd:"0,0,-1"}}\n'
            f'    ];\n'
            f'    var html="";\n'
            f'    axes.forEach(function(ax){{\n'
            f'      var tip=proj(ax.w);\n'
            f'      var tail=proj([-0.4*ax.w[0],-0.4*ax.w[1],-0.4*ax.w[2]]);\n'
            f'      var tx=tip[0].toFixed(1),ty=tip[1].toFixed(1);\n'
            f'      var dx=tip[0]-cx,dy=tip[1]-cy,len=Math.sqrt(dx*dx+dy*dy)||1;\n'
            f'      var nx=-dy/len*3.5,ny=dx/len*3.5;\n'
            f'      var bx1=(tip[0]-dx/len*7+nx).toFixed(1),by1=(tip[1]-dy/len*7+ny).toFixed(1);\n'
            f'      var bx2=(tip[0]-dx/len*7-nx).toFixed(1),by2=(tip[1]-dy/len*7-ny).toFixed(1);\n'
            f'      html+=\'<line x1="\'+cx+\'" y1="\'+cy+\'" x2="\'+tx+\'" y2="\'+ty+\'"\'\n'
            f'           +\' stroke="\'+ax.col+\'" stroke-width="2.5"/>\';\n'
            f'      html+=\'<polygon points="\'+tx+","+ty+" "+bx1+","+by1+" "+bx2+","+by2+\'"\'\n'
            f'           +\' fill="\'+ax.col+\'" data-dir="\'+ax.pd+\'" style="cursor:pointer;"/>\';\n'
            f'      html+=\'<text x="\'+( tip[0]+dx/len*5).toFixed(1)+\'" y="\'+( tip[1]+dy/len*5+3).toFixed(1)+\'"\'\n'
            f'           +\' font-size="9" fill="\'+ax.lcol+\'" font-family="monospace"\'\n'
            f'           +\' data-dir="\'+ax.pd+\'" style="cursor:pointer;">\'+ax.lbl+\'</text>\';\n'
            f'      html+=\'<circle cx="\'+tail[0].toFixed(1)+\'" cy="\'+tail[1].toFixed(1)+\'" r="3.5"\'\n'
            f'           +\' fill="none" stroke="\'+ax.col+\'" stroke-width="1.5"\'\n'
            f'           +\' data-dir="\'+ax.nd+\'" style="cursor:pointer;"/>\';\n'
            f'    }});\n'
            f'    _svg.innerHTML=html;\n'
            f'  }}\n'
            f'  function _axLoop(){{_drawAxes();requestAnimationFrame(_axLoop);}}\n'
            f'  var _ISO_VIEWS=[[1,1,1],[-1,1,1],[-1,-1,1],[1,-1,1]];\n'
            f'  var _ISO_NAMES=["+X+Y+Z","-X+Y+Z","-X-Y+Z","+X-Y+Z"];\n'
            f'  var _isoIdx=0;\n'
            f'  var _isoT;\n'
            f'  (function(){{\n'
            f'    var _ib=document.getElementById("cs-btn-iso-{fig_id_safe}");\n'
            f'    if(_ib)_ib.addEventListener("click",function(){{\n'
            + _iso_lock_gate
            + f'      csSetView_{fig_id_safe}(_ISO_VIEWS[_isoIdx]);\n'
            f'      var fl=document.getElementById("cs-iso-flash-{fig_id_safe}");\n'
            f'      if(fl){{fl.textContent=_ISO_NAMES[_isoIdx];clearTimeout(_isoT);\n'
            f'_isoT=setTimeout(function(){{fl.textContent="";}},1400);}}\n'
            f'      _isoIdx=(_isoIdx+1)%4;\n'
            f'    }});\n'
            f'  }})();\n'
            f'  window.csSetView_{fig_id_safe}=function(dir){{\n'
            f'    if(!_renderer)return;\n'
            f'    var cam=_renderer.getActiveCamera();\n'
            f'    var fp=cam.getFocalPoint(),dist=cam.getDistance();\n'
            f'    var pn=_n3(dir);\n'
            f'    var up=(Math.abs(pn[2])>0.9)?[0,1,0]:[0,0,1];\n'
            f'    cam.setPosition(fp[0]+pn[0]*dist,fp[1]+pn[1]*dist,fp[2]+pn[2]*dist);\n'
            f'    cam.setViewUp(up[0],up[1],up[2]);\n'
            f'    cam.setFocalPoint(fp[0],fp[1],fp[2]);\n'
            f'    _renderer.resetCameraClippingRange();\n'
            f'    if(_iact)_iact.setEnabled(1);\n'
            f'    if(window.renderWindow)window.renderWindow.render();\n'
            f'  }};\n'
        )
    else:
        _js.append(f'  var _renderer=null;\n')
```

- [ ] **Run the full test suite**

```bash
cd /Users/simaocastro/4Dpapers && python -m pytest tests/test_controls_strip.py -v 2>&1 | tail -30
```

Expected: all tests PASS.

- [ ] **Commit implementation**

```bash
cd /Users/simaocastro/4Dpapers && git add _extensions/4dpaper/4dpaper.py && git commit -m "feat: replace chamfered cube with XYZ axis reference + iso cycle button"
```
