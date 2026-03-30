# Lock Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the lock to a permanent top-right corner widget, make it a hard gate blocking field/time/cube interaction, add a "locked" badge, and fix time-slider rendering when the interactor is disabled.

**Architecture:** All changes are inside `_controls_strip_snippet` in `_extensions/4dpaper/4dpaper.py`. The strip loses the lock button; a new fixed `cs-lock-widget-{fig_id_safe}` div sits at `top:4px;right:4px`. A `cs-lock-badge-{fig_id_safe}` div at `right:36px` flashes "locked" for 1.5 s when a blocked interaction fires. The time-slider render call moves before the debounce timeout so it fires immediately.

**Tech Stack:** Python (f-string HTML/JS generation), vtk.js (interactor), pytest

---

## File Structure

- Modify: `_extensions/4dpaper/4dpaper.py` — `_controls_strip_snippet` function (lines 530–1027)
- Test: `tests/test_controls_strip.py`

---

### Task 1: Write failing tests

**Files:**
- Modify: `tests/test_controls_strip.py`

- [ ] **Step 1: Add new HTML tests to `TestControlsStripHtml`**

Insert these after `test_corner_cube_absent_when_orientation_hidden` (around line 118):

```python
def test_lock_widget_present_when_show_lock(self):
    """cs-lock-widget at top:4px;right:4px when show_lock_btn=True."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
    assert 'id="cs-lock-widget-fig_vm"' in html
    assert "top:4px" in html
    assert "right:4px" in html

def test_lock_widget_absent_when_hide(self):
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
    assert 'id="cs-lock-widget-fig_vm"' not in html

def test_lock_badge_present_when_show_lock(self):
    """Badge element present and starts hidden when show_lock_btn=True."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
    assert 'id="cs-lock-badge-fig_vm"' in html
    assert "display:none" in html

def test_lock_badge_absent_when_hide(self):
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
    assert 'id="cs-lock-badge-fig_vm"' not in html

def test_lock_popup_absent(self):
    """cs-pop-lock is no longer emitted."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
    assert 'id="cs-pop-lock-fig_vm"' not in html

def test_lock_button_absent_from_strip(self):
    """cs-btn-lock is no longer in the right strip."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
    assert 'id="cs-btn-lock-fig_vm"' not in html

def test_lock_widget_absent_show_lock_false_orientation_true(self):
    """No lock widget or badge when show_lock_btn=False, even with orientation."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False, show_orientation=True)
    assert 'id="cs-lock-widget-fig_vm"' not in html
    assert 'id="cs-lock-badge-fig_vm"' not in html
```

- [ ] **Step 2: Add new JS tests to `TestControlsStripJs`**

Insert after the last test in `TestControlsStripJs`:

```python
def test_show_locked_badge_function_present(self):
    """_showLockedBadge emitted when show_lock_btn=True."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
    assert "_showLockedBadge" in html

def test_show_locked_badge_absent_when_hide(self):
    """_showLockedBadge NOT emitted when show_lock_btn=False."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
    assert "_showLockedBadge" not in html

def test_set_locked_helper_present(self):
    """_setLocked helper emitted when show_lock_btn=True."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
    assert "_setLocked" in html

def test_toggle_checks_locked_flag(self):
    """if(_locked) guard appears before _CS_ALL loop in csToggle_."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
    js = html.split("<script>", 1)[1] if "<script>" in html else html
    toggle_start = js.find("csToggle_fig_vm")
    assert toggle_start != -1, "csToggle_ not found"
    func_region = js[toggle_start:toggle_start + 300]
    locked_pos = func_region.find("if(_locked)")
    cs_all_pos = func_region.find("_CS_ALL")
    assert locked_pos != -1, "if(_locked) not in csToggle_"
    assert cs_all_pos != -1, "_CS_ALL not in csToggle_"
    assert locked_pos < cs_all_pos, "if(_locked) must come before _CS_ALL loop"

def test_corner_cube_checks_locked_flag(self):
    """SVG click listener contains if(_locked) when both flags True."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=True)
    js = html.split("<script>", 1)[1] if "<script>" in html else html
    svg_var_pos = js.find('getElementById("cs-svg-axes-fig_vm")')
    assert svg_var_pos != -1
    listener_region = js[svg_var_pos:svg_var_pos + 400]
    assert "if(_locked)" in listener_region

def test_corner_cube_no_locked_gate_when_lock_hidden(self):
    """SVG click listener has NO if(_locked) when show_lock_btn=False."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=False)
    js = html.split("<script>", 1)[1] if "<script>" in html else html
    svg_var_pos = js.find('getElementById("cs-svg-axes-fig_vm")')
    assert svg_var_pos != -1
    listener_region = js[svg_var_pos:svg_var_pos + 400]
    assert "if(_locked)" not in listener_region

def test_render_before_debounce(self):
    """renderWindow.render() fires before setTimeout in time slider handler."""
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet(
        "fig-vm",
        time_labels=["0.0", "0.5"], time_data_b64=["AA==", "BB=="],
        time_global_range=[0.0, 1.0], time_field="Vm",
    )
    js = html.split("<script>", 1)[1] if "<script>" in html else html
    slider_pos = js.find("_tSlider")
    assert slider_pos != -1
    slider_section = js[slider_pos:slider_pos + 800]
    render_pos = slider_section.find("renderWindow.render()")
    settimeout_pos = slider_section.find("setTimeout")
    assert render_pos != -1, "renderWindow.render() not in slider handler"
    assert settimeout_pos != -1, "setTimeout not in slider handler"
    assert render_pos < settimeout_pos, "renderWindow.render() must precede setTimeout"
```

- [ ] **Step 3: Update existing tests**

**3a. Delete `test_show_badge_always_declared`** (around line 152–156 — the full method body asserting `_showBadge` is present). Remove it entirely.

**3b. Delete `test_lock_button_in_strip_when_show_lock`** (around line 42–45 — asserts `cs-btn-lock-fig_vm` IS in HTML). The new `test_lock_button_absent_from_strip` covers this element with the correct assertion.

**3c. Delete `test_wildcard_ack_accepted`** (around line 222–225 — asserts `fig_id!=="*"` is present, which came from the `4dpaper-camera-ack` handler). That handler is removed in Step 6; this test will fail after implementation.

**3d. Update `test_strip_div_present`** (around line 38–41 — currently calls `_controls_strip_snippet("fig-vm", show_lock_btn=True)` with no fields/time, so after removing the lock button from the strip, `strip_btns` will be empty and the strip div won't be emitted). Add `show_orientation=True` to ensure the snippet is non-empty, then add a field so the strip div itself is present:

```python
def test_strip_div_present(self):
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet(
        "fig-vm", show_lock_btn=True,
        fields_to_embed=["Vm", "at"], active_field="Vm",
        field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0, 1], "at": [0, 1]},
    )
    assert 'id="cs-strip-fig_vm"' in html
```

**3e. Update `test_popup_panels_present_for_active_features`** (around line 93–97):

```python
def test_popup_panels_present_for_active_features(self):
    mod = _load_4dpaper()
    html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True, show_orientation=True)
    # lock popup removed; axes popup still present
    assert 'id="cs-pop-axes-fig_vm"' in html
    assert 'id="cs-pop-lock-fig_vm"' not in html
```

**3f. `test_lock_toggle_sends_postmessage` — no change needed.** The `4dpaper-lock-toggle` postMessage is still emitted inside the lock widget click handler added in Step 5. The test passes unchanged.

**3g. `test_lock_button_absent_when_hide` — keep as-is.** It asserts `cs-btn-lock-fig_vm` absent when `show_lock_btn=False`. This remains correct (the button never existed in that path and still won't).

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd /Users/simaocastro/4Dpapers
source .venv/bin/activate && pytest tests/test_controls_strip.py -v 2>&1 | tail -40
```

Expected: new tests FAIL (elements/functions not yet implemented), deleted tests gone, `test_popup_panels_present_for_active_features` FAIL.

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/test_controls_strip.py
git commit -m "test: failing tests for lock redesign"
```

---

### Task 2: Implement all four components

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py`

Work entirely inside `_controls_strip_snippet` (lines 530–1027).

#### 2A — Early-exit guard and strip HTML

- [ ] **Step 1: Remove lock button from `strip_btns` and update early-exit guard**

Find this block (around lines 588–609):

```python
    strip_btns = ""
    if show_lock_btn:
        strip_btns += (
            f'<button id="cs-btn-lock-{fig_id_safe}"'
            f' onclick="csToggle_{fig_id_safe}(\'lock\')"'
            f' title="Camera sync" style="{BTN}">&#x1F513;</button>\n'
        )
    if has_fields:
        ...

    if not strip_btns and not show_orientation:
        return ""
```

Replace with (remove the `show_lock_btn` strip button block entirely; update guard):

```python
    strip_btns = ""
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

    if not strip_btns and not show_orientation and not show_lock_btn:
        return ""
```

- [ ] **Step 2: Replace lock popup HTML with lock widget + badge**

Find this block (around lines 633–642):

```python
    lock_pop = ""
    if show_lock_btn:
        lock_pop = (
            f'<div id="cs-pop-lock-{fig_id_safe}" style="{POP}">\n'
            ...
        )
```

Replace entirely with:

```python
    lock_widget = ""
    lock_badge = ""
    if show_lock_btn:
        lock_widget = (
            f'<div id="cs-lock-widget-{fig_id_safe}"'
            f' style="position:fixed;top:4px;right:4px;z-index:9999;'
            f'width:26px;height:26px;background:rgba(20,20,30,0.72);'
            f'border:1px solid rgba(255,255,255,0.18);border-radius:5px;'
            f'cursor:pointer;font-size:13px;'
            f'display:flex;align-items:center;justify-content:center;color:#fff;"'
            f' title="Lock / unlock figure">&#x1F512;</div>\n'
        )
        lock_badge = (
            f'<div id="cs-lock-badge-{fig_id_safe}"'
            f' style="position:fixed;top:4px;right:36px;z-index:9999;'
            f'display:none;background:rgba(20,20,30,0.88);'
            f'border:1px solid rgba(255,255,255,0.12);'
            f'border-radius:4px;padding:2px 6px;'
            f'font-family:monospace;font-size:10px;color:#f88;">locked</div>\n'
        )
```

- [ ] **Step 3: Update `html_block` assembly**

Find line 690:

```python
    html_block += axes_pop + lock_pop + field_pop + time_pop + corner_widget
```

Replace with:

```python
    html_block += axes_pop + lock_widget + lock_badge + field_pop + time_pop + corner_widget
```

#### 2B — JS: `_CS_ALL`, `csToggle_` gate, lock JS block

- [ ] **Step 4: Remove `"lock"` from `_CS_ALL` and add locked gate to `csToggle_`**

Find the `_CS_ALL` / `csToggle_` block (around lines 712–722):

```python
    _js.append(
        f'  var _CS_ALL=["axes","lock","field","time"];\n'
        f'  window.csToggle_{fig_id_safe}=function(name){{\n'
        f'    for(var _i=0;_i<_CS_ALL.length;_i++){{\n'
        ...
    )
```

Replace the entire `_js.append(...)` call for `_CS_ALL` / `csToggle_` with:

```python
    _locked_gate = (
        f'    if(_locked){{_showLockedBadge();return;}}\n'
    ) if show_lock_btn else ''
    _js.append(
        f'  var _CS_ALL=["axes","field","time"];\n'
        f'  window.csToggle_{fig_id_safe}=function(name){{\n'
        + _locked_gate
        + f'    for(var _i=0;_i<_CS_ALL.length;_i++){{\n'
        f'      var _el=document.getElementById("cs-pop-"+_CS_ALL[_i]+"-{fig_id_safe}");\n'
        f'      if(!_el)continue;\n'
        f'      _el.style.display=(_CS_ALL[_i]===name&&_el.style.display==="none")?"flex":"none";\n'
        f'    }}\n'
        + _close_on_toggle
        + f'  }};\n'
    )
```

- [ ] **Step 5: Replace the lock JS block (`_lockBtn` / `_showBadge` section)**

Find the entire `if show_lock_btn: ... else:` block for lock JS (around lines 726–765). It starts with:

```python
    if show_lock_btn:
        _js.append(
            f'  var _lockBtn=document.getElementById("cs-lock-{fig_id_safe}");\n'
```

and ends with the `else:` stub:

```python
    else:
        # No-op stub so camera-ack handler can always call _showBadge
        _js.append(f'  function _showBadge(msg,ok){{}}\n')
```

Replace the entire `if show_lock_btn: ... else: ...` block with:

```python
    if show_lock_btn:
        _js.append(
            f'  var _lockBadgeTimer=null;\n'
            f'  function _showLockedBadge(){{\n'
            f'    var b=document.getElementById("cs-lock-badge-{fig_id_safe}");\n'
            f'    if(!b)return;\n'
            f'    b.style.display="block";\n'
            f'    clearTimeout(_lockBadgeTimer);\n'
            f'    _lockBadgeTimer=setTimeout(function(){{b.style.display="none";}},1500);\n'
            f'  }}\n'
            f'  function _setLocked(v){{\n'
            f'    _locked=v;\n'
            f'    var w=document.getElementById("cs-lock-widget-{fig_id_safe}");\n'
            f'    if(w)w.textContent=v?"\U0001F512":"\U0001F513";\n'
            f'  }}\n'
            f'  if(window.parent!==window){{\n'
            f'    parent.postMessage({{type:"4dpaper-lock-query",fig_id:FIG_ID}},"*");\n'
            f'  }}else{{\n'
            f'    fetch("/camera-lock/"+FIG_ID)\n'
            f'      .then(function(r){{return r.json();}})\n'
            f'      .then(function(d){{_setLocked(!!d.locked);}})\n'
            f'      .catch(function(){{}});\n'
            f'  }}\n'
            f'  (function(){{\n'
            f'    var _lw=document.getElementById("cs-lock-widget-{fig_id_safe}");\n'
            f'    if(_lw)_lw.addEventListener("click",function(){{\n'
            f'      var nv=!_locked;\n'
            f'      _setLocked(nv);\n'
            f'      if(window.parent!==window){{\n'
            f'        parent.postMessage({{type:"4dpaper-lock-toggle",fig_id:FIG_ID,locked:nv}},"*");\n'
            f'      }}else{{\n'
            f'        fetch("/camera-lock/"+FIG_ID,{{'
            f'method:"POST",headers:{{"Content-Type":"application/json"}},'
            f'body:JSON.stringify({{locked:nv}})}}).catch(function(){{_setLocked(!nv);}});\n'
            f'      }}\n'
            f'    }});\n'
            f'  }})();\n'
        )
```

Note: `\U0001F512` and `\U0001F513` are Python Unicode escapes that produce the 🔒 and 🔓 characters in the JS string. These are equivalent to writing the literal emoji directly in the f-string.

- [ ] **Step 6: Remove `4dpaper-camera-ack` handler and `_showBadge` calls**

The postMessage listener is currently three separate `_js.append()` calls at lines 768–784:

```python
# Call A (lines 768–776): opens the listener + camera-ack branch
_js.append(
    f'  window.addEventListener("message",function(e){{\n'
    f'    if(!e.data)return;\n'
    f'    if(e.data.type==="4dpaper-camera-ack"){{\n'
    f'      if(e.data.fig_id!==FIG_ID&&e.data.fig_id!=="*")return;\n'
    f'      _showBadge(...);\n'
    f'    }}\n'
)
# Call B (lines 777–783): lock-state / lock-ack handlers (conditional)
if show_lock_btn:
    _js.append(
        f'    if(e.data.type==="4dpaper-lock-state"...)\n'
        f'    if(e.data.type==="4dpaper-lock-ack"...)\n'
    )
# Call C (line 784): closes the listener
_js.append(f'  }});\n')
```

Replace **all three calls** (A, B, and C) with:

```python
    _js.append(
        f'  window.addEventListener("message",function(e){{\n'
        f'    if(!e.data)return;\n'
    )
    if show_lock_btn:
        _js.append(
            f'    if(e.data.type==="4dpaper-lock-state"&&e.data.fig_id===FIG_ID)'
            f'_setLocked(!!e.data.locked);\n'
            f'    if(e.data.type==="4dpaper-lock-ack"&&e.data.fig_id===FIG_ID){{'
            f'if(e.data.status!=="ok")_setLocked(!_locked);}}\n'
        )
    _js.append(f'  }});\n')
```

The `4dpaper-camera-ack` branch and `_showBadge` call are gone. The lock-state / lock-ack handlers are retained.

- [ ] **Step 7: Remove `_showBadge` calls from `_sendCam`**

Find `_sendCam` (around lines 787–807). It has two `_showBadge` calls in the direct-fetch path:

```python
        f'          .then(function(r){{_showBadge(r.ok?"&#128247; Camera synced":...;}})'
        f').catch(function(){{_showBadge("&#128247; Sync error",false);}});\n'
```

Replace the entire `fetch(...)` call chain in `_sendCam` with one that omits `_showBadge`:

```python
        f'        fetch("/camera/"+FIG_ID,{{method:"POST",'
        f'headers:{{"Content-Type":"application/json"}},body:JSON.stringify(camData)}})\n'
        f'          .catch(function(){{}});\n'
```

#### 2C — JS: Corner cube lock gate

- [ ] **Step 8: Add lock gate to corner cube SVG click listener**

**Important:** The SVG click listener IIFE is **not** a standalone `_js.append()` call. It is embedded as part of the large multi-line `_js.append(...)` call that starts at line 811 (the `_openRotation` / `_closeRotation` / IIFE / math helpers / `_drawAxes` / `_axLoop` / `csSetView_` block). You must edit within that string, not replace a standalone call.

Find these lines within the large `_js.append(...)` starting at line 811:

```python
            f'  (function(){{\n'
            f'    var _svgEl=document.getElementById("cs-svg-axes-{fig_id_safe}");\n'
            f'    if(_svgEl)_svgEl.addEventListener("click",function(){{\n'
            f'      var pop=document.getElementById("cs-pop-axes-{fig_id_safe}");\n'
            f'      if(!pop)return;\n'
            f'      if(pop.style.display==="none"||pop.style.display==="")'
            f'{{_openRotation();}}else{{_closeRotation();}}\n'
            f'    }});\n'
            f'  }})();\n'
```

Replace just those lines (inside the same `_js.append(...)`) with:

```python
            f'  (function(){{\n'
            f'    var _svgEl=document.getElementById("cs-svg-axes-{fig_id_safe}");\n'
            f'    if(_svgEl)_svgEl.addEventListener("click",function(){{\n'
```
then conditionally insert the lock gate line (compute `_cube_lock_gate` before the `_js.append(...)` call):

```python
    _cube_lock_gate = (
        f'      if(_locked){{_showLockedBadge();return;}}\n'
    ) if show_lock_btn else ''
```

and include it in the string concatenation:

```python
            + _cube_lock_gate
            + f'      var pop=document.getElementById("cs-pop-axes-{fig_id_safe}");\n'
            f'      if(!pop)return;\n'
            f'      if(pop.style.display==="none"||pop.style.display==="")'
            f'{{_openRotation();}}else{{_closeRotation();}}\n'
            f'    }});\n'
            f'  }})();\n'
```

The rest of the large `_js.append(...)` (`_renderer`, math helpers, `_drawAxes`, `_axLoop`, `csSetView_`) is unchanged.

#### 2D — JS: Render fix

- [ ] **Step 9: Move `renderWindow.render()` before the debounce timeout**

Find the time slider `input` listener (around lines 999–1016):

```python
            f'            if(_tSlider)_tSlider.addEventListener("input",function(){{\n'
            f'              var idx=parseInt(_tSlider.value);\n'
            f'              if(_tVal&&TIME_LABELS[idx]!==undefined)_tVal.textContent=TIME_LABELS[idx];\n'
            f'              if(_tIdx)_tIdx.textContent=idx;\n'
            f'              clearTimeout(_tTimer);\n'
            f'              _tTimer=setTimeout(function(){{\n'
            f'                var b64=TIME_DATA[idx];if(!b64)return;\n'
            f'                try{{\n'
            f'                  var arr=pd.getPointData().getArrayByName(TIME_FIELD);\n'
            f'                  arr.setData(_decT(b64),1);arr.modified();pd.modified();\n'
            f'                  mp.setScalarRange(GLOBAL_RANGE[0],GLOBAL_RANGE[1]);\n'
            f'                  window.renderWindow.render();\n'
            f'                  try{{parent.postMessage(...);}}'
            f'catch(e2){{}}\n'
            f'                }}catch(err){{console.error("[4dpaper] time step error:",err);}}\n'
            f'              }},100);\n'
            f'            }});\n'
```

Replace with (render immediate, only postMessage debounced):

```python
            f'            if(_tSlider)_tSlider.addEventListener("input",function(){{\n'
            f'              var idx=parseInt(_tSlider.value);\n'
            f'              if(_tVal&&TIME_LABELS[idx]!==undefined)_tVal.textContent=TIME_LABELS[idx];\n'
            f'              if(_tIdx)_tIdx.textContent=idx;\n'
            f'              var b64=TIME_DATA[idx];if(!b64)return;\n'
            f'              try{{\n'
            f'                var arr=pd.getPointData().getArrayByName(TIME_FIELD);\n'
            f'                arr.setData(_decT(b64),1);arr.modified();pd.modified();\n'
            f'                mp.setScalarRange(GLOBAL_RANGE[0],GLOBAL_RANGE[1]);\n'
            f'                window.renderWindow.render();\n'
            f'              }}catch(err){{console.error("[4dpaper] time step error:",err);}}\n'
            f'              clearTimeout(_tTimer);\n'
            f'              _tTimer=setTimeout(function(){{\n'
            f'                try{{parent.postMessage({{type:"4dpaper-field-update",'
            f'fig_id:FIG_ID,data:{{time:String(idx)}}}},"*");}}'
            f'catch(e2){{}}\n'
            f'              }},100);\n'
            f'            }});\n'
```

#### Verify and commit

- [ ] **Step 10: Run the full test suite**

```bash
cd /Users/simaocastro/4Dpapers
source .venv/bin/activate && pytest tests/test_controls_strip.py -v 2>&1 | tail -30
```

Expected: all tests PASS. If any fail, read the failure message carefully — it will point to which element ID or string is missing. Do not add workarounds; fix the root cause in the f-string that generates that element.

- [ ] **Step 11: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py
git commit -m "feat: lock redesign — top-right widget, hard gate, locked badge, render fix"
```

---

## Self-review checklist (for implementer)

After passing tests, verify manually in the generated snippet:

- [ ] `cs-lock-widget-fig_vm` is present with `top:4px;right:4px` when `show_lock_btn=True`
- [ ] `cs-lock-badge-fig_vm` is present with `display:none` when `show_lock_btn=True`
- [ ] `cs-pop-lock-fig_vm` is absent
- [ ] `cs-btn-lock-fig_vm` is absent from strip
- [ ] `_CS_ALL` contains only `["axes","field","time"]`
- [ ] `csToggle_` has `if(_locked)` before the for-loop
- [ ] `_showLockedBadge` declared when `show_lock_btn=True`, absent when `False`
- [ ] SVG click listener has `if(_locked)` when both flags True, not when `show_lock_btn=False`
- [ ] `renderWindow.render()` appears before `setTimeout` in time slider handler
- [ ] `_showBadge` is absent from entire output
- [ ] `4dpaper-camera-ack` handler is absent from message listener
