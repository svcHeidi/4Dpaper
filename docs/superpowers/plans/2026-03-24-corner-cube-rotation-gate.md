# Corner Cube Rotation Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the axes strip button with a permanent live orientation cube at the bottom-left corner of each figure; clicking it enables the vtk.js interactor and shows a preset-view popup, re-locking on close.

**Architecture:** All changes live inside `_controls_strip_snippet` in `_extensions/4dpaper/4dpaper.py`. The corner widget is a `position:fixed; bottom:4px; left:4px` div containing a 28×28px SVG that tracks the camera via a continuous `requestAnimationFrame` loop. The vtk.js interactor is disabled on load (`setEnabled(0)`) and re-enabled only while the popup is open. No new Python functions, no new endpoints, no Lua changes.

**Tech Stack:** Python f-strings for HTML/JS injection, vtk.js interactor API (`getInteractor().setEnabled(0/1)`), SVG for orientation axes, requestAnimationFrame for live tracking.

---

## File Structure

| File | Change |
|---|---|
| `_extensions/4dpaper/4dpaper.py` | Modify `_controls_strip_snippet` — HTML block + JS block |
| `tests/test_controls_strip.py` | Add 12 new tests, update 1 existing test |

---

## Task 1: Write failing tests

**Files:**
- Modify: `tests/test_controls_strip.py`

**Context:** The test file already has 33 passing tests. We add 11 new tests that will FAIL until Task 2 is implemented, and update 1 existing test (`test_axes_button_present_when_show_orientation`) that will FAIL after implementation.

All tests call `_load_4dpaper()` and `mod._controls_strip_snippet(...)` with various arguments. No real vtk rendering is required.

- [ ] **Step 1: Add 4 new HTML tests to `TestControlsStripHtml`**

Append these methods to the `TestControlsStripHtml` class in `tests/test_controls_strip.py`:

```python
    def test_corner_cube_present_when_show_orientation(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        # SVG is now at fixed bottom-left, not inside popup
        assert 'id="cs-svg-axes-fig_vm"' in html
        assert "bottom:4px" in html
        assert "left:4px" in html

    def test_axes_button_absent_from_strip(self):
        """Axes strip button is removed — cube is the only entry point."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-btn-axes-fig_vm"' not in html

    def test_axes_popup_above_corner(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        # Popup anchored above the cube, not in the right-edge strip position
        assert 'id="cs-pop-axes-fig_vm"' in html
        assert "bottom:36px" in html

    def test_corner_cube_absent_when_orientation_hidden(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'id="cs-svg-axes-fig_vm"' not in html
        assert 'id="cs-corner-fig_vm"' not in html

    def test_snippet_not_empty_when_only_orientation(self):
        """Corner cube alone is enough — snippet must not return '' when
        show_lock_btn=False and no fields/time but show_orientation=True."""
        mod = _load_4dpaper()
        result = mod._controls_strip_snippet("fig-vm", show_lock_btn=False, show_orientation=True)
        assert result != ""
        assert 'id="cs-svg-axes-fig_vm"' in result
```

- [ ] **Step 2: Update the existing `test_axes_button_present_when_show_orientation` test**

This test currently asserts the button IS present. After implementation the button is removed. Update it:

Find in `TestControlsStripHtml`:
```python
    def test_axes_button_present_when_show_orientation(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-btn-axes-fig_vm"' in html
```

Replace with:
```python
    def test_axes_button_present_when_show_orientation(self):
        """Axes strip button is replaced by corner cube — must be absent."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-btn-axes-fig_vm"' not in html
```

- [ ] **Step 3: Add 7 new JS tests to `TestControlsStripJs`**

Append these methods to the `TestControlsStripJs` class:

```python
    def test_iact_declared_at_top(self):
        """var _iact = null must be declared (show_orientation=True)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "var _iact=null" in html or "var _iact = null" in html

    def test_interactor_disabled_on_load(self):
        """setEnabled(0) injected into _wR callback when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "setEnabled(0)" in html

    def test_interactor_not_disabled_when_orientation_hidden(self):
        """No setEnabled(0) emitted when show_orientation=False (stays free)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert "setEnabled(0)" not in html

    def test_interactor_enabled_on_open(self):
        """`setEnabled(1)` present inside _openRotation."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "setEnabled(1)" in html

    def test_null_interactor_safe(self):
        """Both _openRotation and _closeRotation guard with if(_iact)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        # Extract just the JS block to avoid false positives in HTML
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        assert "if(_iact)_iact.setEnabled(1)" in js or ("_openRotation" in js and "if(_iact)" in js)
        assert "if(_iact)_iact.setEnabled(0)" in js or ("_closeRotation" in js and "if(_iact)" in js)

    def test_click_handler_on_svg(self):
        """SVG click listener wired to open/close rotation popup."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'cs-svg-axes-fig_vm' in html
        assert 'addEventListener("click"' in html or "addEventListener('click'" in html

    def test_preset_closes_popup(self):
        """_closeRotation() must appear inside csSetView_ function body."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        # Find the csSetView_ function and confirm _closeRotation() is inside it
        start = js.find("csSetView_fig_vm")
        assert start != -1, "csSetView_ not found"
        # Find the closing brace of the function (search for _closeRotation within reasonable range)
        func_body = js[start:start + 1200]
        assert "_closeRotation()" in func_body, "_closeRotation() not inside csSetView_"
```

- [ ] **Step 4: Run tests to confirm they FAIL**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/test_controls_strip.py -q 2>&1 | tail -20
```

Expected: 11+ failures (the 11 new tests + the 1 updated test = 12 failures). Tests from other classes should still pass (33 - 1 updated + 12 new = expect ~33 passing, ~12 failing).

- [ ] **Step 5: Commit**

```bash
git add tests/test_controls_strip.py
git commit -m "test: failing tests for corner cube rotation gate"
```

---

## Task 2: Implement corner cube in `_controls_strip_snippet`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (inside `_controls_strip_snippet`, lines ~555–985)

**Context:** `_controls_strip_snippet` builds an `html_block` (Python string) then a `_js` list of JS fragments joined at the end. We make surgical edits in four places:
1. HTML block — remove axes strip button, relocate SVG to corner widget, reposition popup
2. JS block — add `_iact` declaration + `_openRotation`/`_closeRotation` + click listener + `_closeRotation()` in `csSetView_` + `setEnabled(0)` in `_wR` callback

Read `_extensions/4dpaper/4dpaper.py` lines 555–985 before making any edits to understand the current structure.

### HTML changes

- [ ] **Step 1: Add `AXES_POP` style constant and remove axes button from strip**

In `_controls_strip_snippet`, find the style constants block (where `BTN`, `POP`, `PBTN` are defined, around line 562). Add a new constant `AXES_POP` after `POP`:

```python
    AXES_POP = (
        "position:fixed;bottom:36px;left:4px;"
        "z-index:9998;background:rgba(20,20,30,0.88);"
        "border:1px solid rgba(255,255,255,0.12);border-radius:6px;"
        "padding:8px;font-family:monospace;font-size:11px;color:#eee;"
        "box-shadow:0 4px 12px rgba(0,0,0,0.5);display:none;flex-direction:column;gap:6px;"
    )
```

Then find the `strip_btns` block (around line 581) and **remove** the `show_orientation` branch entirely:

```python
    # REMOVE this block:
    strip_btns = ""
    if show_orientation:
        strip_btns += (
            f'<button id="cs-btn-axes-{fig_id_safe}"'
            f' onclick="csToggle_{fig_id_safe}(\'axes\')"'
            f' title="Orientation / Preset views" style="{BTN}">&#x1F9ED;</button>\n'
        )
```

Replace `strip_btns = ""` block with (keeping lock/field/time branches, just dropping orientation):

```python
    strip_btns = ""
    if show_lock_btn:
        strip_btns += (
            f'<button id="cs-btn-lock-{fig_id_safe}"'
            f' onclick="csToggle_{fig_id_safe}(\'lock\')"'
            f' title="Camera sync" style="{BTN}">&#x1F513;</button>\n'
        )
    if has_fields:
        strip_btns += (
            f'<button id="cs-btn-field-{fig_id_safe}"'
            f' onclick="csToggle_{fig_id_safe}(\'field\')"'
            f' title="Switch field" style="{BTN}">&#x1F3A8;</button>\n'
        )
    if has_time:
        strip_btns += (
            f'<button id="cs-btn-time-{fig_id_safe}"'
            f' onclick="csToggle_{fig_id_safe}(\'time\')"'
            f' title="Time step" style="{BTN}">&#x1F550;</button>\n'
        )
```

- [ ] **Step 2: Rewrite `axes_pop` and add `corner_widget`**

Find the `axes_pop = ""` block (around line 610):

```python
    axes_pop = ""
    if show_orientation:
        axes_pop = (
            f'<div id="cs-pop-axes-{fig_id_safe}" style="{POP}">\n'
            f'  <svg id="cs-svg-axes-{fig_id_safe}" width="72" height="72"'
            f' style="background:rgba(10,10,20,0.6);border-radius:4px;display:block;"></svg>\n'
            f'  <div style="display:flex;gap:2px;flex-wrap:wrap;">\n'
            f'    <button onclick="csSetView_{fig_id_safe}(\'iso\')" style="{PBTN}color:#ccc">Iso</button>\n'
            f'    <button onclick="csSetView_{fig_id_safe}(\'+X\')" style="{PBTN}color:#f88">+X</button>\n'
            f'    <button onclick="csSetView_{fig_id_safe}(\'+Y\')" style="{PBTN}color:#8f8">+Y</button>\n'
            f'    <button onclick="csSetView_{fig_id_safe}(\'+Z\')" style="{PBTN}color:#88f">+Z</button>\n'
            f'  </div>\n'
            f'</div>\n'
        )
```

Replace entirely with:

```python
    corner_widget = ""
    axes_pop = ""
    if show_orientation:
        corner_widget = (
            f'<div id="cs-corner-{fig_id_safe}"'
            f' style="position:fixed;bottom:4px;left:4px;z-index:9999;">\n'
            f'  <svg id="cs-svg-axes-{fig_id_safe}" width="28" height="28"'
            f' style="background:rgba(10,10,20,0.55);border:1px solid rgba(255,255,255,0.12);'
            f'border-radius:4px;display:block;cursor:pointer;" title="Click to rotate"></svg>\n'
            f'</div>\n'
        )
        axes_pop = (
            f'<div id="cs-pop-axes-{fig_id_safe}" style="{AXES_POP}">\n'
            f'  <div style="display:flex;gap:2px;flex-wrap:wrap;">\n'
            f'    <button onclick="csSetView_{fig_id_safe}(\'iso\')" style="{PBTN}color:#ccc">Iso</button>\n'
            f'    <button onclick="csSetView_{fig_id_safe}(\'+X\')" style="{PBTN}color:#f66">+X</button>\n'
            f'    <button onclick="csSetView_{fig_id_safe}(\'+Y\')" style="{PBTN}color:#6f6">+Y</button>\n'
            f'    <button onclick="csSetView_{fig_id_safe}(\'+Z\')" style="{PBTN}color:#66f">+Z</button>\n'
            f'  </div>\n'
            f'</div>\n'
        )
```

- [ ] **Step 3: Update `html_block` to include `corner_widget`**

Find the `html_block = (...)` assignment (around line 674):

```python
    html_block = (
        f'<div id="cs-strip-{fig_id_safe}" style="position:fixed;right:4px;top:50%;'
        f'transform:translateY(-50%);z-index:9999;display:flex;flex-direction:column;gap:4px;">\n'
        + strip_btns
        + f'</div>\n'
        + axes_pop + lock_pop + field_pop + time_pop
    )
```

Update to include `corner_widget` and handle the strip disappearing when `strip_btns` is empty:

```python
    html_block = ""
    if strip_btns:
        html_block += (
            f'<div id="cs-strip-{fig_id_safe}" style="position:fixed;right:4px;top:50%;'
            f'transform:translateY(-50%);z-index:9999;display:flex;flex-direction:column;gap:4px;">\n'
            + strip_btns
            + f'</div>\n'
        )
    html_block += axes_pop + lock_pop + field_pop + time_pop + corner_widget
```

Also update the early-exit guard that was checking `strip_btns`. Find:

```python
    if not strip_btns:
        return ""
```

Replace with:

```python
    if not strip_btns and not show_orientation:
        return ""
```

This is important: when only `show_orientation=True` and both `show_lock_btn=False` and no fields/time, the corner cube should still be rendered even though `strip_btns` is empty.

### JS changes

- [ ] **Step 4: Add `_iact` declaration and modify `csToggle_`**

Find the `_js.append(f'  var _locked=false;\n')` line (around line 706).

**Before** that line, add `_iact` declaration (conditional on `show_orientation`):

```python
    if show_orientation:
        _js.append(f'  var _iact=null;\n')
```

Then find the `csToggle_` block (around line 694):

```python
    _js.append(
        f'  var _CS_ALL=["axes","lock","field","time"];\n'
        f'  window.csToggle_{fig_id_safe}=function(name){{\n'
        f'    for(var _i=0;_i<_CS_ALL.length;_i++){{\n'
        f'      var _el=document.getElementById("cs-pop-"+_CS_ALL[_i]+"-{fig_id_safe}");\n'
        f'      if(!_el)continue;\n'
        f'      _el.style.display=(_CS_ALL[_i]===name&&_el.style.display==="none")?"flex":"none";\n'
        f'    }}\n'
        f'  }};\n'
    )
```

Replace with (adds interactor re-lock when axes popup is dismissed by opening another panel):

```python
    _close_on_toggle = (
        f'    if(name!=="axes"){{if(_iact)_iact.setEnabled(0);}}\n'
    ) if show_orientation else ''
    _js.append(
        f'  var _CS_ALL=["axes","lock","field","time"];\n'
        f'  window.csToggle_{fig_id_safe}=function(name){{\n'
        f'    for(var _i=0;_i<_CS_ALL.length;_i++){{\n'
        f'      var _el=document.getElementById("cs-pop-"+_CS_ALL[_i]+"-{fig_id_safe}");\n'
        f'      if(!_el)continue;\n'
        f'      _el.style.display=(_CS_ALL[_i]===name&&_el.style.display==="none")?"flex":"none";\n'
        f'    }}\n'
        + _close_on_toggle
        + f'  }};\n'
    )
```

- [ ] **Step 5: Add `_openRotation`, `_closeRotation`, SVG click handler, and update `csSetView_`**

Find the orientation helpers block (around line 791) that starts with `if show_orientation:`. Currently it contains `_n3`, `_cr`, `_dt`, `_drawAxes`, `_axLoop`, `csSetView_`.

Replace the entire `if show_orientation:` / `else:` block with:

```python
    if show_orientation:
        _js.append(
            f'  function _openRotation(){{\n'
            f'    if(_iact)_iact.setEnabled(1);\n'
            f'    document.getElementById("cs-pop-axes-{fig_id_safe}").style.display="flex";\n'
            f'  }}\n'
            f'  function _closeRotation(){{\n'
            f'    if(_iact)_iact.setEnabled(0);\n'
            f'    document.getElementById("cs-pop-axes-{fig_id_safe}").style.display="none";\n'
            f'  }}\n'
            f'  (function(){{\n'
            f'    var _svgEl=document.getElementById("cs-svg-axes-{fig_id_safe}");\n'
            f'    if(_svgEl)_svgEl.addEventListener("click",function(){{\n'
            f'      var pop=document.getElementById("cs-pop-axes-{fig_id_safe}");\n'
            f'      if(!pop)return;\n'
            f'      if(pop.style.display==="none"||pop.style.display==="")'
            f'{{_openRotation();}}else{{_closeRotation();}}\n'
            f'    }});\n'
            f'  }})();\n'
            f'  var _renderer=null;\n'
            f'  function _n3(v){{var l=Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);'
            f'return l<1e-10?[0,0,1]:[v[0]/l,v[1]/l,v[2]/l];}}\n'
            f'  function _cr(a,b){{return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}}\n'
            f'  function _dt(a,b){{return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}}\n'
            f'  var _svg=document.getElementById("cs-svg-axes-{fig_id_safe}");\n'
            f'  function _drawAxes(){{\n'
            f'    if(!_renderer||!_svg)return;\n'
            f'    var cam=_renderer.getActiveCamera();\n'
            f'    var pos=cam.getPosition(),fp=cam.getFocalPoint(),vup=cam.getViewUp();\n'
            f'    var vd=_n3([fp[0]-pos[0],fp[1]-pos[1],fp[2]-pos[2]]);\n'
            f'    var right=_n3(_cr(vd,vup)),up=_cr(right,vd);\n'
            f'    var cx=14,cy=14,R=10;\n'
            f'    var axes=[{{v:[1,0,0],col:"#f66",lbl:"x"}},{{v:[0,1,0],col:"#6f6",lbl:"y"}},{{v:[0,0,1],col:"#66f",lbl:"z"}}];\n'
            f'    axes.sort(function(a,b){{return _dt(a.v,vd)-_dt(b.v,vd);}});\n'
            f'    var lines="";\n'
            f'    for(var i=0;i<axes.length;i++){{\n'
            f'      var ax=axes[i];\n'
            f'      var sx=cx+R*_dt(ax.v,right),sy=cy-R*_dt(ax.v,up);\n'
            f'      var al=_dt(ax.v,vd)<0?"0.35":"1";\n'
            f'      lines+=\'<line x1="\'+cx+\'" y1="\'+cy+\'" x2="\'+sx.toFixed(1)+\'" y2="\'+sy.toFixed(1)+\'"'
            f' stroke="\'+ax.col+\'" stroke-width="2" stroke-opacity="\'+al+\'"/>\';\n'
            f'      lines+=\'<circle cx="\'+sx.toFixed(1)+\'" cy="\'+sy.toFixed(1)+\'" r="3"'
            f' fill="\'+ax.col+\'" fill-opacity="\'+al+\'"/>\';\n'
            f'      lines+=\'<text x="\'+( sx+(sx-cx>0?4:-8) ).toFixed(1)+\'" y="\'+( sy+(sy-cy>0?7:-3) ).toFixed(1)+\'"'
            f' font-size="7" fill="\'+ax.col+\'" fill-opacity="\'+al+\'" font-family="monospace">\'+ax.lbl+\'</text>\';\n'
            f'    }}\n'
            f'    _svg.innerHTML=lines;\n'
            f'  }}\n'
            f'  function _axLoop(){{_drawAxes();requestAnimationFrame(_axLoop);}}\n'
            f'  window.csSetView_{fig_id_safe}=function(view){{\n'
            f'    if(!_renderer)return;\n'
            f'    var cam=_renderer.getActiveCamera();\n'
            f'    var fp=cam.getFocalPoint(),dist=cam.getDistance();\n'
            f'    var dirs={{"iso":{{p:[1,1,1],u:[0,0,1]}},"+X":{{p:[1,0,0],u:[0,0,1]}},'
            f'"+Y":{{p:[0,1,0],u:[0,0,1]}},"+Z":{{p:[0,0,1],u:[0,1,0]}}}};\n'
            f'    var d=dirs[view];if(!d)return;\n'
            f'    var pn=_n3(d.p);\n'
            f'    cam.setPosition(fp[0]+pn[0]*dist,fp[1]+pn[1]*dist,fp[2]+pn[2]*dist);\n'
            f'    cam.setViewUp(d.u[0],d.u[1],d.u[2]);\n'
            f'    cam.setFocalPoint(fp[0],fp[1],fp[2]);\n'
            f'    _renderer.resetCameraClippingRange();\n'
            f'    if(window.renderWindow)window.renderWindow.render();\n'
            f'    _closeRotation();\n'
            f'  }};\n'
        )
    else:
        _js.append(f'  var _renderer=null;\n')
```

- [ ] **Step 6: Add `_iact` initialisation and `setEnabled(0)` inside `_wR` renderer callback**

Find the `_wR` renderer polling block (around line 841). It currently starts like:

```python
    _axLoop_call = f'          _axLoop();\n' if show_orientation else ''
    _js.append(
        f'  (function _wR(){{\n'
        ...
        f'          _renderer=_r;\n'
        + _axLoop_call +
        f'          document.addEventListener("pointerup",...
```

Add an `_iact_lock` fragment to the renderer-found block:

```python
    _axLoop_call = f'          _axLoop();\n' if show_orientation else ''
    _iact_lock = (
        f'          _iact=window.renderWindow.getInteractor();\n'
        f'          if(_iact)_iact.setEnabled(0);\n'
    ) if show_orientation else ''
    _js.append(
        f'  (function _wR(){{\n'
        f'    var rw=window.renderWindow;\n'
        f'    if(rw&&rw.getRenderers){{\n'
        f'      var rs=rw.getRenderers();\n'
        f'      for(var _ri=0;_ri<rs.length;_ri++){{\n'
        f'        var _r=rs[_ri];\n'
        f'        if(_r&&_r.getActors&&_r.getActors().length>0){{\n'
        f'          _renderer=_r;\n'
        + _axLoop_call
        + _iact_lock
        + f'          document.addEventListener("pointerup",function(){{_sendCam(_renderer);}});\n'
        f'          document.addEventListener("mouseup",function(){{_sendCam(_renderer);}});\n'
        f'          document.addEventListener("touchend",function(){{_sendCam(_renderer);}});\n'
        f'          window.addEventListener("message",function(e){{\n'
        f'            if(!e.data||e.data.type!=="4dpaper-camera-apply")return;\n'
        f'            var cam=e.data.camera;if(!cam)return;\n'
        f'            var c=_renderer.getActiveCamera();\n'
        f'            if(cam.position)c.setPosition(cam.position[0],cam.position[1],cam.position[2]);\n'
        f'            if(cam.focal_point)c.setFocalPoint(cam.focal_point[0],cam.focal_point[1],cam.focal_point[2]);\n'
        f'            if(cam.view_up)c.setViewUp(cam.view_up[0],cam.view_up[1],cam.view_up[2]);\n'
        f'            if(cam.parallel_scale!=null)c.setParallelScale(cam.parallel_scale);\n'
        f'            if(cam.parallel_projection!=null)c.setParallelProjection(!!cam.parallel_projection);\n'
        f'            window.renderWindow.render();\n'
        f'          }});\n'
        f'          return;\n'
        f'        }}\n'
        f'      }}\n'
        f'    }}\n'
        f'    setTimeout(_wR,200);\n'
        f'  }})();\n'
    )
```

- [ ] **Step 7: Run full test suite**

```bash
cd /Users/simaocastro/4Dpapers && .venv/bin/pytest tests/ -q -k "not Video and not video" 2>&1 | tail -10
```

Expected: all pass. If any fail, read the error, fix the implementation, and re-run. Do not proceed until all tests pass.

- [ ] **Step 8: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_controls_strip.py
git commit -m "feat: corner cube rotation gate — click to unlock vtk.js interactor"
```
