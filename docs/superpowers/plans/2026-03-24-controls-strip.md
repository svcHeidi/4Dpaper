# Controls Strip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace four separate HTML/JS overlays injected into each vtk.js figure (lock button, camera badge, field switcher, time slider, orientation axes) with a single thin right-edge icon strip whose icon buttons reveal popup panels — leaving the figure surface completely clean.

**Architecture:** A new `_controls_strip_snippet(fig_id, ...)` function replaces the four existing `_camera_sync_snippet`, `_field_sync_snippet`, `_time_sync_snippet`, and `_orientation_snippet` functions. It produces a single `<script>` + HTML block injected before `</body>`. A thin vertical icon strip floats on the right edge (position:fixed, right:4px, vertically centred); each icon opens one floating popup panel to its left. Exactly one panel is open at a time. All existing JS logic (postMessage, camera apply, field switching, time scrubbing, renderer polling) is preserved verbatim — only the UI chrome moves inside the new popup layout.

**Tech Stack:** Python f-strings generating HTML/JS; vtk.js/trame standalone HTML figures; `_extensions/4dpaper/4dpaper.py`; pytest.

---

## File structure

| File | Change |
|------|--------|
| `_extensions/4dpaper/4dpaper.py` | Add `_controls_strip_snippet`; modify `generate_html_figure`; delete old 4 snippet functions |
| `tests/test_controls_strip.py` | New — structural tests for the new snippet |
| `tests/test_extension.py` | Update tests that reference old element IDs or call old snippet functions directly |
| `tests/test_panel_sync.py` | Update `TestSnippetForSync` tests (they call `_camera_sync_snippet` which will be removed) |

---

## Background: what the old snippet functions do

`_camera_sync_snippet(fig_id, show_lock_btn)` (line ~630 in 4dpaper.py):
- Renders a lock button (`<button id="lock-btn-{id}">`) top-left
- Renders a camera badge div top-right
- JS: debounced `sendCamera` on pointerup/mouseup → `parent.postMessage` or `fetch /camera/<id>`
- JS: `window.addEventListener("message")` for `4dpaper-camera-ack`, `4dpaper-lock-state`, `4dpaper-lock-ack`
- JS: `waitRenderer` polling loop (used only internally — NOT a global function)
- JS: on `4dpaper-camera-apply` message → applies camera to renderer

`_field_sync_snippet(fig_id, available_fields, cur_field, field_data_b64, field_ranges)` (line ~789):
- Renders `<div>` bottom-left with `<select id="field-sel-{id}">` and a badge span
- JS: `waitMapper` polling loop; on `<select>` change → decode base64 Float32Array → `arr.setData()` → re-render

`_time_sync_snippet(fig_id, time_labels, time_data_b64, global_range, initial_idx, original_field)` (line ~950):
- Renders `<div>` centred bottom with `<input type="range" id="time-slider-{id}">`
- JS: `waitMapper` polling loop; on slider input → decode array → `arr.setData()` → re-render

`_orientation_snippet(fig_id)` (line ~530):
- Renders SVG axes widget + Iso/+X/+Y/+Z buttons
- JS: inline `_waitR` polling → gets renderer → rAF loop updating SVG via camera dot-products
- JS: `window.csSetView_{fig_id_safe}` global for preset views

**Key implementation notes:**
1. `fig_id_safe` MUST use `.replace("</","<\\/").replace('"','').replace("-","_")` — hyphens are invalid JS identifiers.
2. `_locked` and `_showBadge` MUST be declared unconditionally at the top of the IIFE — even when `show_lock_btn=False` — because `_sendCam` calls `if(_locked)return` and `_showBadge` is called from the always-emitted camera-ack message handler.
3. Build the JS block using a **list + `"".join()`** pattern, NOT chained conditional `+` expressions, to avoid silent Python concatenation gaps.

---

## Task 1: Write failing tests for `_controls_strip_snippet`

**Files:**
- Create: `tests/test_controls_strip.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the unified controls strip snippet."""
from __future__ import annotations
import importlib.util
from pathlib import Path


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestControlsStripExists:
    def test_function_exists(self):
        mod = _load_4dpaper()
        assert hasattr(mod, "_controls_strip_snippet")

    def test_returns_string(self):
        mod = _load_4dpaper()
        result = mod._controls_strip_snippet("fig-vm")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_empty_when_all_hidden(self):
        mod = _load_4dpaper()
        result = mod._controls_strip_snippet(
            "fig-vm", show_lock_btn=False, show_orientation=False
        )
        assert result == ""


class TestControlsStripHtml:
    def test_strip_div_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'id="cs-strip-fig_vm"' in html

    def test_lock_button_in_strip_when_show_lock(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'id="cs-btn-lock-fig_vm"' in html

    def test_lock_button_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert 'id="cs-btn-lock-fig_vm"' not in html

    def test_axes_button_present_when_show_orientation(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-btn-axes-fig_vm"' in html

    def test_axes_button_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'id="cs-btn-axes-fig_vm"' not in html

    def test_field_button_present_when_multiple_fields(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert 'id="cs-btn-field-fig_vm"' in html

    def test_field_button_absent_when_single_field(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm"], active_field="Vm",
            field_data_b64={"Vm": "AA=="}, field_ranges={"Vm": [0,1]},
        )
        assert 'id="cs-btn-field-fig_vm"' not in html

    def test_time_button_present_when_time_data(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.0", "0.5"], time_data_b64=["AA==", "BB=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        assert 'id="cs-btn-time-fig_vm"' in html

    def test_time_button_absent_when_no_time(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert 'id="cs-btn-time-fig_vm"' not in html

    def test_popup_panels_present_for_active_features(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True, show_orientation=True)
        assert 'id="cs-pop-lock-fig_vm"' in html
        assert 'id="cs-pop-axes-fig_vm"' in html


class TestControlsStripJs:
    def test_toggle_function_defined(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "csToggle_fig_vm" in html

    def test_toggle_references_popup_ids(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "cs-pop-" in html

    def test_hyphens_replaced_in_js_identifier(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("ts-vm-0")
        assert "csToggle_ts_vm_0" in html
        assert "csToggle_ts-vm-0" not in html

    def test_locked_always_declared(self):
        """_locked must be declared even when show_lock_btn=False (used by _sendCam)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert "var _locked=false" in html or "var _locked = false" in html

    def test_show_badge_always_declared(self):
        """_showBadge must exist even when show_lock_btn=False (called by camera-ack handler)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert "_showBadge" in html


class TestControlsStripCameraLogic:
    def test_camera_apply_listener_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "4dpaper-camera-apply" in html

    def test_camera_sets_position_focal_viewup(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "setPosition" in html
        assert "setFocalPoint" in html
        assert "setViewUp" in html

    def test_wildcard_ack_accepted(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'fig_id!=="*"' in html or 'fig_id !== "*"' in html

    def test_send_camera_on_pointerup(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "pointerup" in html

    def test_lock_toggle_sends_postmessage(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "4dpaper-lock-toggle" in html


class TestControlsStripOrientationLogic:
    def test_axes_svg_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-svg-axes-fig_vm"' in html

    def test_preset_view_function_defined(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "csSetView_fig_vm" in html

    def test_preset_buttons_call_set_view(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "csSetView_fig_vm('iso')" in html or 'csSetView_fig_vm("iso")' in html

    def test_axes_raf_loop_present(self):
        """Axes rAF loop (_axLoop) must exist when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "_axLoop" in html

    def test_axes_raf_loop_absent_when_hidden(self):
        """When show_orientation=False, _axLoop must not be emitted."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert "_axLoop" not in html


class TestControlsStripFieldLogic:
    def test_field_select_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert 'id="cs-field-sel-fig_vm"' in html

    def test_field_data_embedded(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AABB", "at": "CCDD"}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert "AABB" in html
        assert "CCDD" in html

    def test_field_setdata_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert "setData" in html
        assert "setScalarRange" in html


class TestControlsStripTimeLogic:
    def test_time_slider_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.0", "0.5", "1.0"], time_data_b64=["AA==", "BB==", "CC=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        assert 'id="cs-time-slider-fig_vm"' in html

    def test_time_labels_embedded(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.001", "0.005"], time_data_b64=["AA==", "BB=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        assert "0.001" in html
        assert "0.005" in html
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
.venv/bin/pytest tests/test_controls_strip.py -q 2>&1 | tail -10
```
Expected: all fail with `AttributeError: module 'fourDpaper' has no attribute '_controls_strip_snippet'`

---

## Task 2: Implement `_controls_strip_snippet`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` — add `_controls_strip_snippet` before `_camera_sync_snippet` (around line 630)

The function replaces `_camera_sync_snippet`, `_field_sync_snippet`, `_time_sync_snippet`, and `_orientation_snippet` in one block. Do NOT delete the old functions yet — that is Task 3.

**Critical implementation rules:**
1. Build the JS using a `_js = []` / `"".join(_js)` pattern — never chain conditional `+` expressions in one big parenthesised string.
2. Always declare `var _locked=false` and `function _showBadge(...)` unconditionally; only the *UI* (button, badge div, query) is conditional on `show_lock_btn`.

- [ ] **Step 1: Add the function**

Insert at the section header `# ── Camera sync snippet ───` (around line 630), BEFORE `def _camera_sync_snippet`:

```python
# ── Unified controls strip snippet ────────────────────────────────────────────

def _controls_strip_snippet(
    fig_id: str,
    show_lock_btn: bool = True,
    show_orientation: bool = True,
    fields_to_embed: list[str] | None = None,
    active_field: str = "",
    field_data_b64: dict | None = None,
    field_ranges: dict | None = None,
    time_labels: list[str] | None = None,
    time_data_b64: list[str] | None = None,
    time_global_range: list[float] | None = None,
    time_idx: int = 0,
    time_field: str = "",
) -> str:
    """
    Return a combined HTML+JS block that adds a right-edge icon strip to a
    vtk.js figure, with popup panels for camera lock, orientation axes/presets,
    field switching, and time scrubbing.

    The figure surface itself has zero UI overlay — all controls live in the
    strip. Exactly one panel is open at a time; clicking the active icon closes
    it.

    Replaces _camera_sync_snippet, _field_sync_snippet, _time_sync_snippet,
    and _orientation_snippet.
    """
    fig_id_js = json.dumps(fig_id).replace("</", "<\\/")
    # Hyphens are invalid in JS identifiers. Use underscores in function names
    # and element IDs that appear inside onclick="" attributes.
    fig_id_safe = fig_id.replace("</", "<\\/").replace('"', '').replace("-", "_")

    has_fields = bool(fields_to_embed and len(fields_to_embed) > 1)
    has_time = bool(time_labels and len(time_labels) > 1 and time_data_b64)
    n_time = len(time_data_b64) if time_data_b64 else 0

    # ── shared style constants ──────────────────────────────────────────────
    BTN = (
        "width:26px;height:26px;background:rgba(20,20,30,0.72);"
        "border:1px solid rgba(255,255,255,0.18);border-radius:5px;"
        "cursor:pointer;font-size:13px;line-height:1;color:#fff;"
        "display:flex;align-items:center;justify-content:center;"
    )
    POP = (
        "position:fixed;right:38px;top:50%;transform:translateY(-50%);"
        "z-index:9998;background:rgba(20,20,30,0.88);"
        "border:1px solid rgba(255,255,255,0.12);border-radius:6px;"
        "padding:10px;font-family:monospace;font-size:11px;color:#eee;"
        "box-shadow:0 4px 12px rgba(0,0,0,0.5);display:none;flex-direction:column;gap:6px;"
        "min-width:120px;"
    )
    PBTN = (
        "font-size:9px;padding:1px 5px;background:rgba(40,40,60,0.85);"
        "border:1px solid #555;border-radius:3px;cursor:pointer;"
    )

    # ── strip buttons ───────────────────────────────────────────────────────
    strip_btns = ""
    if show_orientation:
        strip_btns += (
            f'<button id="cs-btn-axes-{fig_id_safe}"'
            f' onclick="csToggle_{fig_id_safe}(\'axes\')"'
            f' title="Orientation / Preset views" style="{BTN}">&#x1F9ED;</button>\n'
        )
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

    if not strip_btns:
        return ""

    # ── axes popup HTML ─────────────────────────────────────────────────────
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

    # ── lock popup HTML ─────────────────────────────────────────────────────
    lock_pop = ""
    if show_lock_btn:
        lock_pop = (
            f'<div id="cs-pop-lock-{fig_id_safe}" style="{POP}">\n'
            f'  <div id="cs-badge-{fig_id_safe}"'
            f' style="display:none;padding:2px 6px;border-radius:2px;font-size:11px;"></div>\n'
            f'  <button id="cs-lock-{fig_id_safe}"'
            f' style="{PBTN}color:#ccc;font-size:11px;padding:3px 8px;">&#x1F513; Unlock</button>\n'
            f'</div>\n'
        )

    # ── field popup HTML ────────────────────────────────────────────────────
    field_pop = ""
    if has_fields:
        field_opts = "".join(
            f'<option value="{f}"{"  selected" if f == active_field else ""}>{f}</option>'
            for f in (fields_to_embed or [])
        )
        field_pop = (
            f'<div id="cs-pop-field-{fig_id_safe}" style="{POP}">\n'
            f'  <label style="display:flex;flex-direction:column;gap:4px;">Field:\n'
            f'    <select id="cs-field-sel-{fig_id_safe}"'
            f' style="background:#333;color:#fff;border:1px solid #555;border-radius:3px;">\n'
            f'      {field_opts}\n'
            f'    </select>\n'
            f'  </label>\n'
            f'  <span id="cs-field-badge-{fig_id_safe}"'
            f' style="display:none;padding:2px 6px;border-radius:2px;font-size:10px;"></span>\n'
            f'</div>\n'
        )

    # ── time popup HTML ─────────────────────────────────────────────────────
    time_pop = ""
    if has_time:
        initial_label = (
            time_labels[time_idx] if time_idx < len(time_labels) else str(time_idx)
        )
        time_pop = (
            f'<div id="cs-pop-time-{fig_id_safe}" style="{POP}">\n'
            f'  <div style="display:flex;justify-content:space-between;gap:8px;">\n'
            f'    <span style="color:#aaa;">t&nbsp;=&nbsp;'
            f'<span id="cs-time-val-{fig_id_safe}">{initial_label}</span></span>\n'
            f'    <span style="color:#666;font-size:10px;">'
            f'<span id="cs-time-idx-{fig_id_safe}">{time_idx}</span>/{n_time - 1}</span>\n'
            f'  </div>\n'
            f'  <input type="range" id="cs-time-slider-{fig_id_safe}"'
            f' min="0" max="{n_time - 1}" value="{time_idx}"\n'
            f'    style="width:160px;cursor:pointer;accent-color:#4a9eff;">\n'
            f'</div>\n'
        )

    # ── assemble HTML ───────────────────────────────────────────────────────
    html_block = (
        f'<div id="cs-strip-{fig_id_safe}" style="position:fixed;right:4px;top:50%;'
        f'transform:translateY(-50%);z-index:9999;display:flex;flex-direction:column;gap:4px;">\n'
        + strip_btns
        + f'</div>\n'
        + axes_pop + lock_pop + field_pop + time_pop
    )

    # ── JS data serialisation ───────────────────────────────────────────────
    active_field_js = json.dumps(active_field).replace("</", "<\\/")
    field_data_js = json.dumps(field_data_b64 or {}).replace("</", "<\\/")
    field_ranges_js = json.dumps(field_ranges or {}).replace("</", "<\\/")
    time_field_js = json.dumps(time_field or active_field).replace("</", "<\\/")
    time_data_js = json.dumps(time_data_b64 or []).replace("</", "<\\/")
    time_labels_js = json.dumps(time_labels or []).replace("</", "<\\/")
    global_range_js = json.dumps(time_global_range or [0.0, 1.0])

    # ── Build JS using a list to avoid + operator / conditional string pitfalls ──
    _js = []

    _js.append(f'  var FIG_ID={fig_id_js};\n')

    # Panel toggle (always emitted)
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

    # _locked + _showBadge: ALWAYS declared (sendCam uses _locked; camera-ack handler uses _showBadge)
    _js.append(f'  var _locked=false;\n')
    if show_lock_btn:
        _js.append(
            f'  var _lockBtn=document.getElementById("cs-lock-{fig_id_safe}");\n'
            f'  var _badge=document.getElementById("cs-badge-{fig_id_safe}");\n'
            f'  var _hideTimer=null;\n'
            f'  function _setLocked(v){{\n'
            f'    _locked=v;\n'
            f'    if(_lockBtn)_lockBtn.innerHTML=(v?"&#x1F512; Lock":"&#x1F513; Unlock");\n'
            f'  }}\n'
            f'  function _showBadge(msg,ok){{\n'
            f'    if(!_badge)return;\n'
            f'    _badge.innerHTML=msg;\n'
            f'    _badge.style.background=ok?"rgba(0,140,0,0.85)":"rgba(180,0,0,0.85)";\n'
            f'    _badge.style.display="block";\n'
            f'    clearTimeout(_hideTimer);\n'
            f'    if(ok)_hideTimer=setTimeout(function(){{_badge.style.display="none";}},3000);\n'
            f'  }}\n'
            # Query initial lock state
            f'  if(window.parent!==window){{\n'
            f'    parent.postMessage({{type:"4dpaper-lock-query",fig_id:FIG_ID}},"*");\n'
            f'  }}else{{\n'
            f'    fetch("/camera-lock/"+FIG_ID)\n'
            f'      .then(function(r){{return r.json();}})\n'
            f'      .then(function(d){{_setLocked(!!d.locked);}})\n'
            f'      .catch(function(){{}});\n'
            f'  }}\n'
            # Lock button click handler
            f'  if(_lockBtn)_lockBtn.addEventListener("click",function(){{\n'
            f'    var nv=!_locked;\n'
            f'    _setLocked(nv);\n'
            f'    if(window.parent!==window){{\n'
            f'      parent.postMessage({{type:"4dpaper-lock-toggle",fig_id:FIG_ID,locked:nv}},"*");\n'
            f'    }}else{{\n'
            f'      fetch("/camera-lock/"+FIG_ID,{{'
            f'method:"POST",headers:{{"Content-Type":"application/json"}},'
            f'body:JSON.stringify({{locked:nv}})}}).catch(function(){{_setLocked(!nv);}});\n'
            f'    }}\n'
            f'  }});\n'
        )
    else:
        # No-op stub so camera-ack handler can always call _showBadge safely
        _js.append(f'  function _showBadge(msg,ok){{}}\n')

    # postMessage listener: camera-ack + lock-state/ack (always emitted)
    _js.append(
        f'  window.addEventListener("message",function(e){{\n'
        f'    if(!e.data)return;\n'
        f'    if(e.data.type==="4dpaper-camera-ack"){{\n'
        f'      if(e.data.fig_id!==FIG_ID&&e.data.fig_id!=="*")return;\n'
        f'      _showBadge(e.data.status==="ok"?"&#128247; Camera synced":"&#128247; Sync error",'
        f'e.data.status==="ok");\n'
        f'    }}\n'
    )
    if show_lock_btn:
        _js.append(
            f'    if(e.data.type==="4dpaper-lock-state"&&e.data.fig_id===FIG_ID)'
            f'_setLocked(!!e.data.locked);\n'
            f'    if(e.data.type==="4dpaper-lock-ack"&&e.data.fig_id===FIG_ID){{'
            f'if(e.data.status!=="ok")_setLocked(!_locked);}}\n'
        )
    _js.append(f'  }});\n')

    # sendCam function (always emitted)
    _js.append(
        f'  var _camTimer=null;\n'
        f'  function _sendCam(renderer){{\n'
        f'    if(_locked)return;\n'
        f'    clearTimeout(_camTimer);\n'
        f'    _camTimer=setTimeout(function(){{\n'
        f'      var cam=renderer.getActiveCamera();\n'
        f'      var camData={{position:cam.getPosition(),focal_point:cam.getFocalPoint(),'
        f'view_up:cam.getViewUp(),parallel_scale:cam.getParallelScale(),'
        f'parallel_projection:cam.getParallelProjection()?1:0}};\n'
        f'      if(window.parent!==window){{\n'
        f'        parent.postMessage({{type:"4dpaper-camera",fig_id:FIG_ID,camera:camData}},"*");\n'
        f'      }}else{{\n'
        f'        fetch("/camera/"+FIG_ID,{{method:"POST",'
        f'headers:{{"Content-Type":"application/json"}},body:JSON.stringify(camData)}})\n'
        f'          .then(function(r){{_showBadge(r.ok?"&#128247; Camera synced":"&#128247; Sync error",r.ok);}}'
        f').catch(function(){{_showBadge("&#128247; Sync error",false);}});\n'
        f'      }}\n'
        f'    }},300);\n'
        f'  }}\n'
    )

    # Orientation helpers (conditional)
    if show_orientation:
        _js.append(
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
            f'    var cx=36,cy=36,R=26;\n'
            f'    var axes=[{{v:[1,0,0],col:"#f55",lbl:"X"}},{{v:[0,1,0],col:"#5c5",lbl:"Y"}},{{v:[0,0,1],col:"#55f",lbl:"Z"}}];\n'
            f'    axes.sort(function(a,b){{return _dt(a.v,vd)-_dt(b.v,vd);}});\n'
            f'    var lines="";\n'
            f'    for(var i=0;i<axes.length;i++){{\n'
            f'      var ax=axes[i];\n'
            f'      var sx=cx+R*_dt(ax.v,right),sy=cy-R*_dt(ax.v,up);\n'
            f'      var al=_dt(ax.v,vd)<0?"0.35":"1";\n'
            f'      lines+=\'<line x1="\'+cx+\'" y1="\'+cy+\'" x2="\'+sx.toFixed(1)+\'" y2="\'+sy.toFixed(1)+\'"'
            f' stroke="\'+ax.col+\'" stroke-width="2.5" stroke-opacity="\'+al+\'"/>\';\n'
            f'      lines+=\'<circle cx="\'+sx.toFixed(1)+\'" cy="\'+sy.toFixed(1)+\'" r="4"'
            f' fill="\'+ax.col+\'" fill-opacity="\'+al+\'"/>\';\n'
            f'      lines+=\'<text x="\'+( sx+(sx-cx>0?6:-10) ).toFixed(1)+\'" y="\'+( sy+(sy-cy>0?8:-4) ).toFixed(1)+\'"'
            f' font-size="9" fill="\'+ax.col+\'" fill-opacity="\'+al+\'" font-family="monospace">\'+ax.lbl+\'</text>\';\n'
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
            f'  }};\n'
        )
    else:
        _js.append(f'  var _renderer=null;\n')

    # Renderer polling → sets _renderer, registers event listeners
    _axLoop_call = f'          _axLoop();\n' if show_orientation else ''
    _js.append(
        f'  (function _wR(){{\n'
        f'    var rw=window.renderWindow;\n'
        f'    if(rw&&rw.getRenderers){{\n'
        f'      var rs=rw.getRenderers();\n'
        f'      for(var _ri=0;_ri<rs.length;_ri++){{\n'
        f'        var _r=rs[_ri];\n'
        f'        if(_r&&_r.getActors&&_r.getActors().length>0){{\n'
        f'          _renderer=_r;\n'
        + _axLoop_call +
        f'          document.addEventListener("pointerup",function(){{_sendCam(_renderer);}});\n'
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

    # Field switcher JS (conditional)
    if has_fields:
        _js.append(
            f'  var FIELD_DATA={field_data_js};\n'
            f'  var FIELD_RANGES={field_ranges_js};\n'
            f'  var ORIG_FIELD={active_field_js};\n'
            f'  var _fSel=document.getElementById("cs-field-sel-{fig_id_safe}");\n'
            f'  var _fBadge=document.getElementById("cs-field-badge-{fig_id_safe}");\n'
            f'  function _decF(b64){{var bin=atob(b64);var by=new Uint8Array(bin.length);'
            f'for(var i=0;i<bin.length;i++)by[i]=bin.charCodeAt(i);return new Float32Array(by.buffer);}}\n'
            f'  (function _wM(){{\n'
            f'    var rw=window.renderWindow;\n'
            f'    if(rw&&rw.getRenderers){{\n'
            f'      var rs=rw.getRenderers();\n'
            f'      for(var _ri=0;_ri<rs.length;_ri++){{\n'
            f'        var _r=rs[_ri];if(!_r||!_r.getActors)continue;\n'
            f'        var acts=_r.getActors();\n'
            f'        for(var _ai=0;_ai<acts.length;_ai++){{\n'
            f'          var act=acts[_ai];if(!act||!act.getMapper)continue;\n'
            f'          var mp=act.getMapper();if(!mp||!mp.getInputData)continue;\n'
            f'          var pd=mp.getInputData();\n'
            f'          if(pd&&pd.getPointData&&pd.getPointData().getArrayByName(ORIG_FIELD)){{\n'
            f'            if(_fSel)_fSel.addEventListener("change",function(){{\n'
            f'              var f=_fSel.value;\n'
            f'              if(!FIELD_DATA[f]&&f!==ORIG_FIELD)return;\n'
            f'              try{{\n'
            f'                if(_fBadge){{_fBadge.innerHTML="&#8230;";'
            f'_fBadge.style.background="#555";_fBadge.style.display="inline-block";}}\n'
            f'                var arr=pd.getPointData().getArrayByName(ORIG_FIELD);\n'
            f'                if(FIELD_DATA[f])arr.setData(_decF(FIELD_DATA[f]),1);\n'
            f'                arr.modified();pd.modified();\n'
            f'                var rng=FIELD_RANGES[f];\n'
            f'                if(rng)mp.setScalarRange(rng[0],rng[1]);\n'
            f'                try{{var a2=_r.getActors2D?_r.getActors2D():[];'
            f'for(var k=0;k<a2.length;k++)if(a2[k].setTitle)a2[k].setTitle(f);}}'
            f'catch(e2){{}}\n'
            f'                window.renderWindow.render();\n'
            f'                if(_fBadge){{_fBadge.innerHTML="&#10003; "+f;'
            f'_fBadge.style.background="rgba(0,140,0,0.85)";'
            f'setTimeout(function(){{_fBadge.style.display="none";}},2000);}}\n'
            f'                try{{parent.postMessage({{type:"4dpaper-field-update",'
            f'fig_id:FIG_ID,data:{{field:f}}}},"*");}}'
            f'catch(e3){{}}\n'
            f'              }}catch(err){{\n'
            f'                if(_fBadge){{_fBadge.innerHTML="&#10007; error";'
            f'_fBadge.style.background="rgba(180,0,0,0.85)";'
            f'_fBadge.style.display="inline-block";}}\n'
            f'                console.error("[4dpaper] field switch error:",err);\n'
            f'              }}\n'
            f'            }});\n'
            f'            return;\n'
            f'          }}\n'
            f'        }}\n'
            f'      }}\n'
            f'    }}\n'
            f'    setTimeout(_wM,200);\n'
            f'  }})();\n'
        )

    # Time scrubber JS (conditional)
    if has_time:
        _js.append(
            f'  var TIME_DATA={time_data_js};\n'
            f'  var TIME_LABELS={time_labels_js};\n'
            f'  var GLOBAL_RANGE={global_range_js};\n'
            f'  var TIME_FIELD={time_field_js};\n'
            f'  var _tSlider=document.getElementById("cs-time-slider-{fig_id_safe}");\n'
            f'  var _tVal=document.getElementById("cs-time-val-{fig_id_safe}");\n'
            f'  var _tIdx=document.getElementById("cs-time-idx-{fig_id_safe}");\n'
            f'  var _tTimer=null;\n'
            f'  function _decT(b64){{var bin=atob(b64);var by=new Uint8Array(bin.length);'
            f'for(var i=0;i<bin.length;i++)by[i]=bin.charCodeAt(i);return new Float32Array(by.buffer);}}\n'
            f'  (function _wT(){{\n'
            f'    var rw=window.renderWindow;\n'
            f'    if(rw&&rw.getRenderers){{\n'
            f'      var rs=rw.getRenderers();\n'
            f'      for(var _ri=0;_ri<rs.length;_ri++){{\n'
            f'        var _r=rs[_ri];if(!_r||!_r.getActors)continue;\n'
            f'        var acts=_r.getActors();\n'
            f'        for(var _ai=0;_ai<acts.length;_ai++){{\n'
            f'          var act=acts[_ai];if(!act||!act.getMapper)continue;\n'
            f'          var mp=act.getMapper();if(!mp||!mp.getInputData)continue;\n'
            f'          var pd=mp.getInputData();\n'
            f'          if(pd&&pd.getPointData&&pd.getPointData().getArrayByName(TIME_FIELD)){{\n'
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
            f'                  try{{parent.postMessage({{type:"4dpaper-field-update",'
            f'fig_id:FIG_ID,data:{{time:String(idx)}}}},"*");}}'
            f'catch(e2){{}}\n'
            f'                }}catch(err){{console.error("[4dpaper] time step error:",err);}}\n'
            f'              }},100);\n'
            f'            }});\n'
            f'            return;\n'
            f'          }}\n'
            f'        }}\n'
            f'      }}\n'
            f'    }}\n'
            f'    setTimeout(_wT,200);\n'
            f'  }})();\n'
        )

    js_block = f'<script>\n(function(){{\n' + "".join(_js) + f'}})();\n</script>\n'
    return html_block + js_block
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_controls_strip.py -q 2>&1 | tail -15
```
Expected: All tests pass.

- [ ] **Step 3: Fix any failures**

Common issues and their fixes:
- `var _locked=false` test fails → ensure the `_js.append(f'  var _locked=false;\n')` line is before the `if show_lock_btn:` conditional block
- `_showBadge` test when `show_lock_btn=False` fails → ensure the `else:` branch after `if show_lock_btn:` has `_js.append(f'  function _showBadge(msg,ok){{}}\n')`
- `_axLoop` absent when `show_orientation=False` → `_axLoop()` call must be gated on `show_orientation`

- [ ] **Step 4: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_controls_strip.py
git commit -m "feat: _controls_strip_snippet — unified right-edge icon strip replacing 4 overlays"
```

---

## Task 3: Wire `_controls_strip_snippet` into `generate_html_figure`, update tests, remove old functions

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py`
- Modify: `tests/test_extension.py`
- Modify: `tests/test_panel_sync.py`

### Step 1: Verify `generate_html_from_vtu` and `generate_pvsm_figure` do not call old snippets

Before deleting anything, run:
```bash
grep -n "_camera_sync_snippet\|_field_sync_snippet\|_time_sync_snippet\|_orientation_snippet" \
  _extensions/4dpaper/4dpaper.py
```
Expected: only results in `generate_html_figure` and the function definitions themselves. If any other function calls them, update those calls first before deleting.

### Step 2: Update `generate_html_figure` injection block

Find the injection block (search for `inj_html = (`):

```python
# OLD — 4 separate snippet calls:
if camera_preview_only:
    orient = _orientation_snippet(fig_id) + "\n" if show_orientation else ""
    inj_html = (
        _camera_sync_snippet(fig_id, show_lock_btn=show_lock_btn)
        + "\n"
        + orient
        + "</body>"
    )
else:
    orient = _orientation_snippet(fig_id) + "\n" if show_orientation else ""
    inj_html = (
        _camera_sync_snippet(fig_id, show_lock_btn=show_lock_btn)
        + "\n"
        + _field_sync_snippet(fig_id, fields_to_embed, field, field_data_b64, field_ranges)
        + "\n"
        + _time_sync_snippet(fig_id, time_labels, time_data_b64, time_global_range, idx, field)
        + "\n"
        + orient
        + "</body>"
    )
```

Replace with:

```python
# NEW — single strip snippet
if camera_preview_only:
    inj_html = _controls_strip_snippet(
        fig_id=fig_id,
        show_lock_btn=show_lock_btn,
        show_orientation=show_orientation,
    ) + "\n</body>"
else:
    inj_html = _controls_strip_snippet(
        fig_id=fig_id,
        show_lock_btn=show_lock_btn,
        show_orientation=show_orientation,
        fields_to_embed=fields_to_embed,
        active_field=field,
        field_data_b64=field_data_b64,
        field_ranges=field_ranges,
        time_labels=time_labels,
        time_data_b64=time_data_b64,
        time_global_range=time_global_range,
        time_idx=idx,
        time_field=field,
    ) + "\n</body>"
```

(`fields_to_embed` is a list at this point in `generate_html_figure` — it is built as `fields_to_embed = list(available_fields) if available_fields else [field]` earlier in the function. Passing it to `_controls_strip_snippet` is correct; `None` is handled by the function's defaults but will not occur here.)

### Step 3: Run full test suite to identify all failures

```bash
.venv/bin/pytest tests/ -q -k "not Video and not video" 2>&1 | tail -25
```

Expected failures:
- `tests/test_panel_sync.py::TestSnippetForSync::*` — call `mod._camera_sync_snippet()` directly
- `tests/test_extension.py` tests checking old element IDs (`lock-btn-`, `camera-badge-`, `field-sel-`, `time-ctrl-`, `time-slider-`, `orient-widget-`, `orient-svg-`)
- `tests/test_extension.py::TestTimeSyncSnippet::*` — class calls `mod._time_sync_snippet()` directly
- `tests/test_extension.py` field snippet tests — call `mod._field_sync_snippet()` directly

### Step 4: Update `tests/test_panel_sync.py` — `TestSnippetForSync`

Replace the three methods to call `_controls_strip_snippet`:

```python
class TestSnippetForSync:
    def test_wildcard_ack_accepted(self):
        mod = _load_4dpaper()
        snippet = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'fig_id!=="*"' in snippet or 'fig_id !== "*"' in snippet

    def test_camera_apply_listener_present(self):
        mod = _load_4dpaper()
        snippet = mod._controls_strip_snippet("fig-vm")
        assert "4dpaper-camera-apply" in snippet

    def test_camera_apply_sets_camera_position(self):
        mod = _load_4dpaper()
        snippet = mod._controls_strip_snippet("fig-vm")
        assert "setPosition" in snippet
        assert "setFocalPoint" in snippet
        assert "setViewUp" in snippet
```

### Step 5: Update `tests/test_extension.py` — element ID renames and deleted function classes

**Element ID mapping** (search for each old prefix and update to new):

| Old ID prefix | New ID prefix |
|---------------|---------------|
| `lock-btn-` | `cs-btn-lock-` or `cs-lock-` |
| `camera-badge-` | `cs-badge-` |
| `field-sel-` | `cs-field-sel-` |
| `time-ctrl-` | `cs-pop-time-` |
| `time-slider-` | `cs-time-slider-` |
| `orient-widget-` | `cs-strip-` |
| `orient-svg-` | `cs-svg-axes-` |

Search for full-form IDs too (e.g. `camera-badge-fig-vm` → `cs-badge-fig-vm`).

**Classes to delete or rewrite:**
- `TestTimeSyncSnippet` — calls `mod._time_sync_snippet()` which will be deleted. **Delete this class.** Time sync is now tested via `TestControlsStripTimeLogic` in `test_controls_strip.py`.
- Any class that calls `mod._field_sync_snippet()` directly — **delete those test methods** (field sync is covered by `TestControlsStripFieldLogic`).
- Any class that calls `mod._camera_sync_snippet()` directly other than `TestSnippetForSync` (already handled above) — **delete those test methods**.
- Any class that calls `mod._orientation_snippet()` directly — **delete those test methods**.

Run:
```bash
.venv/bin/pytest tests/ -q -k "not Video and not video" 2>&1 | tail -5
```
Expected: same pass count as before the failing tests were removed.

### Step 6: Delete the four old snippet functions

Remove these functions from `4dpaper.py`:
- `_orientation_snippet` (starts around line 530)
- `_camera_sync_snippet` (starts around line 630)
- `_field_sync_snippet` (starts around line 789)
- `_time_sync_snippet` (starts around line 950)

Run tests one final time:
```bash
.venv/bin/pytest tests/ -q -k "not Video and not video" 2>&1 | tail -5
```
Expected: passes with no new failures.

### Step 7: Commit

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_extension.py tests/test_panel_sync.py
git commit -m "refactor: wire controls strip into generate_html_figure, remove old snippet fns"
```
