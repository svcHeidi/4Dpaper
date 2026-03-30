# Camera Lock, Panel Sync, and Timeseries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-figure camera lock, panel camera sync mode, and a new `{{< 4d-timeseries >}}` shortcode that auto-generates a synced N×1 panel from a single source at N equally-spaced time steps.

**Architecture:** Camera lock is a new Tornado endpoint + padlock button in each vtk.js iframe; panel sync adds a `camera="sync"` kwarg that makes all subfigures share one camera file and embeds the composite HTML as a single Lua iframe; timeseries is a new shortcode that expands into a panel-compatible dict at pre-render time and flows through the existing panel pipeline.

**Tech Stack:** Python 3.12, Tornado, PyVista, vtk.js, Lua (Quarto shortcode API), PIL, pytest.

**Spec:** `docs/superpowers/specs/2026-03-23-camera-lock-panel-sync-timeseries-design.md`

---

## File Map

| File | Task(s) | What changes |
|------|---------|--------------|
| `dashboard/camera_plugin.py` | 1 | Add `CameraLockHandler`, update `ROUTES` |
| `_extensions/4dpaper/4dpaper.py` | 2, 3, 4, 5, 6, 7, 8 | `_camera_sync_snippet`, `generate_png_figure`, `generate_panel_html`, `generate_panel_png`, `parse_panel_shortcodes`, `parse_timeseries_shortcodes` (new), `_expand_timeseries_steps` (new), `main()` |
| `_extensions/4dpaper/shortcodes.lua` | 3, 7, 9 | `_RELAY_SCRIPT`, `fourd_panel`, `fourd_timeseries` (new) |
| `tests/test_camera_lock.py` | 1, 2 | New test file |
| `tests/test_panel_sync.py` | 4, 5, 6, 7 | New test file |
| `tests/test_timeseries.py` | 8, 9 | New test file |

---

## Task 1: CameraLockHandler — backend endpoint

**Files:**
- Modify: `dashboard/camera_plugin.py:62-64`
- Create: `tests/test_camera_lock.py`

The lock state is persisted at `state/camera_<fig_id>_lock.json`. GET returns `{"locked": false}` when file is absent. POST writes `{"locked": true/false}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_camera_lock.py`:

```python
"""Tests for the CameraLockHandler Tornado endpoint."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_lock_handler(body_bytes: bytes = b"") -> "CameraLockHandler":
    from dashboard.camera_plugin import CameraLockHandler
    request = MagicMock()
    request.body = body_bytes
    handler = CameraLockHandler.__new__(CameraLockHandler)
    handler.request = request
    handler.write = MagicMock()
    handler.set_status = MagicMock()
    handler.finish = MagicMock()
    return handler


def test_camera_lock_handler_in_routes():
    from dashboard.camera_plugin import CameraLockHandler, ROUTES
    assert CameraLockHandler is not None
    patterns = [r for r, _ in ROUTES]
    assert any("camera-lock" in p for p in patterns)


def test_lock_get_returns_false_when_absent(tmp_path):
    (tmp_path / "state").mkdir()
    handler = _make_lock_handler()
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.get("fig-vm")
    handler.write.assert_called_once_with({"locked": False})


def test_lock_get_returns_saved_state(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "camera_fig-vm_lock.json").write_text('{"locked": true}')
    handler = _make_lock_handler()
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.get("fig-vm")
    handler.write.assert_called_once_with({"locked": True})


def test_lock_post_writes_file(tmp_path):
    (tmp_path / "state").mkdir()
    body = json.dumps({"locked": True}).encode()
    handler = _make_lock_handler(body)
    with patch("dashboard.camera_plugin._PROJECT_ROOT", tmp_path):
        handler.post("fig-vm")
    lock_path = tmp_path / "state" / "camera_fig-vm_lock.json"
    assert lock_path.exists()
    data = json.loads(lock_path.read_text())
    assert data == {"locked": True}
    handler.write.assert_called_once_with({"status": "ok"})


def test_lock_post_invalid_fig_id_returns_400():
    handler = _make_lock_handler(b'{"locked": true}')
    handler.post("../evil; rm -rf")
    handler.set_status.assert_called_once_with(400)


def test_lock_get_invalid_fig_id_returns_400():
    handler = _make_lock_handler()
    handler.get("../evil")
    handler.set_status.assert_called_once_with(400)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/simaocastro/4Dpapers
python -m pytest tests/test_camera_lock.py -v 2>&1 | head -40
```

Expected: `ImportError` or `AssertionError` — `CameraLockHandler` does not exist yet.

- [ ] **Step 3: Add `CameraLockHandler` to `dashboard/camera_plugin.py`**

Append after the `CameraHandler` class (before the `ROUTES` line at line 62):

```python
class CameraLockHandler(tornado.web.RequestHandler):
    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def get(self, fig_id: str) -> None:
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400)
            self.write({"status": "error"})
            return
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        if lock_path.exists():
            self.write(json.loads(lock_path.read_text()))
        else:
            self.write({"locked": False})

    def post(self, fig_id: str) -> None:
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400)
            self.write({"status": "error"})
            return
        body = json.loads(self.request.body)
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        lock_path.write_text(json.dumps({"locked": bool(body.get("locked", False))}))
        self.write({"status": "ok"})
```

Replace the existing `ROUTES` list:

```python
ROUTES = [
    (r"/camera/(?P<fig_id>[^/]+)", CameraHandler),
    (r"/camera-lock/(?P<fig_id>[^/]+)", CameraLockHandler),
]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_camera_lock.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/camera_plugin.py tests/test_camera_lock.py
git commit -m "feat: add CameraLockHandler GET/POST endpoint"
```

---

## Task 2: Camera lock UI in `_camera_sync_snippet`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py:457-554` (`_camera_sync_snippet`)
- Modify: `tests/test_camera_lock.py` (add snippet shape tests)

The lock button is a fixed-position element (top-left). The existing single-purpose message listener (line 486–500) must be restructured into a multi-branch listener because the current pattern exits immediately for any non-`4dpaper-camera-ack` type, making it impossible to add lock-state/lock-ack branches.

- [ ] **Step 1: Add snippet shape tests to `tests/test_camera_lock.py`**

Append to the file:

```python
def _load_4dpaper():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lock_button_in_snippet():
    mod = _load_4dpaper()
    snippet = mod._camera_sync_snippet("fig-vm")
    assert 'id="lock-btn-fig-vm"' in snippet
    assert "🔓" in snippet


def test_snippet_has_set_locked_function():
    mod = _load_4dpaper()
    snippet = mod._camera_sync_snippet("fig-vm")
    assert "function setLocked" in snippet
    assert "lockBtn.textContent" in snippet


def test_snippet_has_lock_guard_in_send_camera():
    mod = _load_4dpaper()
    snippet = mod._camera_sync_snippet("fig-vm")
    assert "if(locked)return" in snippet or "if (locked) return" in snippet


def test_snippet_queries_lock_on_load():
    mod = _load_4dpaper()
    snippet = mod._camera_sync_snippet("fig-vm")
    assert "4dpaper-lock-query" in snippet


def test_snippet_handles_lock_state_message():
    mod = _load_4dpaper()
    snippet = mod._camera_sync_snippet("fig-vm")
    assert "4dpaper-lock-state" in snippet


def test_snippet_handles_lock_ack_message():
    mod = _load_4dpaper()
    snippet = mod._camera_sync_snippet("fig-vm")
    assert "4dpaper-lock-ack" in snippet
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_camera_lock.py::test_lock_button_in_snippet -v
```

Expected: `AssertionError` — lock button not yet in snippet.

- [ ] **Step 3: Rewrite `_camera_sync_snippet` in `_extensions/4dpaper/4dpaper.py`**

The function starts at line 457. Replace its body (lines 472–554). The new version adds:
1. Lock button `<button>` HTML element (before the existing badge `<div>`)
2. Lock state variables and `setLocked()` before `waitRenderer`
3. Lock initialization query on load
4. Lock button click handler
5. Restructured message listener (multi-branch, not early-exit)
6. `sendCamera()` guard at the top

New body (replace everything from `fig_id_js = ...` to the final `f'</script>'`):

```python
    fig_id_js = json.dumps(fig_id).replace("</", "<\\/")
    fig_id_safe = fig_id.replace("</", "<\\/")
    return (
        # Lock button (top-left)
        f'<button id="lock-btn-{fig_id_safe}" style="position:fixed;top:8px;left:8px;'
        f'background:rgba(0,0,0,0.45);border:none;border-radius:4px;'
        f'font-size:14px;cursor:pointer;padding:4px 6px;z-index:9999;'
        f'color:#fff;opacity:0.7;" title="Lock camera">\U0001f513</button>\n'
        # Camera sync badge (top-right, hidden until sync)
        f'<div id="camera-badge-{fig_id_safe}" style="position:fixed;top:8px;right:8px;'
        f'display:none;color:#fff;padding:4px 8px;'
        f'border-radius:4px;font-size:11px;font-family:monospace;'
        f'z-index:9999;pointer-events:none;"></div>\n'
        f'<script>\n'
        f'(function(){{\n'
        f'  var FIG_ID={fig_id_js};\n'
        f'  var badge=document.getElementById("camera-badge-{fig_id_safe}");\n'
        f'  var timer=null, hideTimer=null;\n'
        # Lock state
        f'  var locked=false;\n'
        f'  var lockBtn=document.getElementById("lock-btn-{fig_id_safe}");\n'
        f'  function setLocked(v){{\n'
        f'    locked=v;\n'
        f'    lockBtn.textContent=v?"\U0001f512":"\U0001f513";\n'
        f'    lockBtn.style.opacity=v?"1":"0.7";\n'
        f'  }}\n'
        # Initialize lock state from server on load
        f'  if(window.parent!==window){{\n'
        f'    parent.postMessage({{type:"4dpaper-lock-query",fig_id:FIG_ID}},"*");\n'
        f'  }}else{{\n'
        f'    fetch("/camera-lock/"+FIG_ID)\n'
        f'      .then(function(r){{return r.json();}})\n'
        f'      .then(function(d){{setLocked(!!d.locked);}})\n'
        f'      .catch(function(){{}});\n'
        f'  }}\n'
        # Lock button click handler
        f'  lockBtn.addEventListener("click",function(){{\n'
        f'    var newVal=!locked;\n'
        f'    var expected=newVal;\n'
        f'    setLocked(newVal);\n'
        f'    if(window.parent!==window){{\n'
        f'      parent.postMessage({{type:"4dpaper-lock-toggle",fig_id:FIG_ID,locked:newVal}},"*");\n'
        f'    }}else{{\n'
        f'      fetch("/camera-lock/"+FIG_ID,{{\n'
        f'        method:"POST",headers:{{"Content-Type":"application/json"}},\n'
        f'        body:JSON.stringify({{locked:newVal}})\n'
        f'      }}).catch(function(){{setLocked(!expected);}});\n'
        f'    }}\n'
        f'  }});\n'
        # Multi-branch message listener (replaces the old single-purpose early-exit listener)
        f'  window.addEventListener("message",function(e){{\n'
        f'    if(!e.data)return;\n'
        f'    if(e.data.type==="4dpaper-camera-ack"){{\n'
        f'      if(e.data.fig_id!==FIG_ID&&e.data.fig_id!=="*")return;\n'
        f'      if(e.data.status==="ok"){{\n'
        f'        badge.innerHTML="&#128247; Camera synced";\n'
        f'        badge.style.background="rgba(0,140,0,0.85)";\n'
        f'        badge.style.display="block";\n'
        f'        clearTimeout(hideTimer);\n'
        f'        hideTimer=setTimeout(function(){{badge.style.display="none";}},3000);\n'
        f'      }}else{{\n'
        f'        badge.innerHTML="&#128247; Sync error";\n'
        f'        badge.style.background="rgba(180,0,0,0.85)";\n'
        f'        badge.style.display="block";\n'
        f'      }}\n'
        f'    }}\n'
        f'    if(e.data.type==="4dpaper-lock-state"&&e.data.fig_id===FIG_ID){{\n'
        f'      setLocked(!!e.data.locked);\n'
        f'    }}\n'
        f'    if(e.data.type==="4dpaper-lock-ack"&&e.data.fig_id===FIG_ID){{\n'
        f'      if(e.data.status!=="ok")setLocked(!locked);\n'
        f'    }}\n'
        f'  }});\n'
        f'  function sendCamera(renderer){{\n'
        f'    if(locked)return;\n'
        f'    clearTimeout(timer);\n'
        f'    timer=setTimeout(function(){{\n'
        f'      var cam=renderer.getActiveCamera();\n'
        f'      var camData={{\n'
        f'        position:cam.getPosition(),\n'
        f'        focal_point:cam.getFocalPoint(),\n'
        f'        view_up:cam.getViewUp(),\n'
        f'        parallel_scale:cam.getParallelScale(),\n'
        f'        parallel_projection:cam.getParallelProjection()?1:0\n'
        f'      }};\n'
        f'      if(window.parent!==window){{\n'
        f'        parent.postMessage({{type:"4dpaper-camera",fig_id:FIG_ID,camera:camData}},"*");\n'
        f'      }}else{{\n'
        f'        fetch("/camera/"+FIG_ID,{{\n'
        f'          method:"POST",headers:{{"Content-Type":"application/json"}},\n'
        f'          body:JSON.stringify(camData)\n'
        f'        }}).then(function(r){{\n'
        f'          badge.innerHTML="&#128247; Camera synced";\n'
        f'          badge.style.background=r.ok?"rgba(0,140,0,0.85)":"rgba(180,0,0,0.85)";\n'
        f'          badge.style.display="block";clearTimeout(hideTimer);\n'
        f'          if(r.ok)hideTimer=setTimeout(function(){{badge.style.display="none";}},3000);\n'
        f'        }}).catch(function(){{\n'
        f'          badge.innerHTML="&#128247; Sync error";\n'
        f'          badge.style.background="rgba(180,0,0,0.85)";\n'
        f'          badge.style.display="block";\n'
        f'        }});\n'
        f'      }}\n'
        f'    }},300);\n'
        f'  }}\n'
        f'  function waitRenderer(cb){{\n'
        f'    function check(){{\n'
        f'      var rw=window.renderWindow;\n'
        f'      if(rw&&rw.getRenderers){{\n'
        f'        var renderers=rw.getRenderers();\n'
        f'        for(var i=0;i<renderers.length;i++){{\n'
        f'          var r=renderers[i];\n'
        f'          if(r&&r.getActors&&r.getActors().length>0){{cb(r);return;}}\n'
        f'        }}\n'
        f'      }}\n'
        f'      setTimeout(check,200);\n'
        f'    }}\n'
        f'    check();\n'
        f'  }}\n'
        f'  waitRenderer(function(renderer){{\n'
        f'    document.addEventListener("pointerup",function(){{sendCamera(renderer);}});\n'
        f'    document.addEventListener("mouseup",function(){{sendCamera(renderer);}});\n'
        f'    document.addEventListener("touchend",function(){{sendCamera(renderer);}});\n'
        f'  }});\n'
        f'}})();\n'
        f'</script>'
    )
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_camera_lock.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Also run the existing test suite to check for regressions**

```bash
python -m pytest tests/test_extension.py tests/test_styles.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_camera_lock.py
git commit -m "feat: add camera lock padlock button to vtk.js iframes"
```

---

## Task 3: `_RELAY_SCRIPT` — fix camera ack routing and add lock handlers

**Files:**
- Modify: `_extensions/4dpaper/shortcodes.lua:98-128` (inside `_RELAY_SCRIPT`)

Currently, `4dpaper-camera` ack is sent only to `_f2.contentWindow` (the Camera Setup modal iframe). It must also go to `e.source` so figure iframes get their own badges, and sync panel composites can re-relay it. Add lock-query and lock-toggle handlers.

- [ ] **Step 1: Write tests in `tests/test_camera_lock.py`**

Append to the file:

```python
def test_relay_script_sends_ack_to_source():
    """_RELAY_SCRIPT camera handler must send ack to both _f2 and e.source."""
    content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
    # After fix, both conditions must appear in the camera handler section
    assert "e.source.postMessage" in content
    assert "4dpaper-camera-ack" in content


def test_relay_script_has_lock_query_handler():
    content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
    assert "4dpaper-lock-query" in content
    assert "4dpaper-lock-state" in content


def test_relay_script_has_lock_toggle_handler():
    content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
    assert "4dpaper-lock-toggle" in content
    assert "4dpaper-lock-ack" in content
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_camera_lock.py::test_relay_script_sends_ack_to_source -v
```

Expected: `AssertionError`.

- [ ] **Step 3: Edit `_extensions/4dpaper/shortcodes.lua`**

Replace the `4dpaper-camera` handler block (lines 98–116) with the updated version that also sends ack to `e.source`, then append two new `else if` branches for lock-query and lock-toggle before the closing `}` of the message listener (line 129):

Find and replace this block in `_RELAY_SCRIPT`:
```
    } else if(e.data.type==="4dpaper-camera"){
      var figId=e.data.fig_id;
      var _f2=document.getElementById('fourd-cam-iframe');
      var _ss2=document.getElementById('fourd-cam-sttxt');
      fetch('/camera/'+figId,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(e.data.camera)
      }).then(function(r){
        if(_ss2){
          if(r.ok){_ss2.textContent='\u2713 Camera saved \u2014 click \u201cRebuild HTML\u201d to apply';_ss2.style.color='#4caf50';}
          else{_ss2.textContent='\u2717 Save failed (server error)';_ss2.style.color='#f44336';}
        }
        if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(
          {type:'4dpaper-camera-ack',fig_id:figId,status:r.ok?'ok':'error'},'*');
      }).catch(function(){
        if(_ss2){_ss2.textContent='\u2717 Save failed (network error)';_ss2.style.color='#f44336';}
        if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(
          {type:'4dpaper-camera-ack',fig_id:figId,status:'error'},'*');
      });
```

Replace with:
```
    } else if(e.data.type==="4dpaper-camera"){
      var figId=e.data.fig_id;
      var _f2=document.getElementById('fourd-cam-iframe');
      var _ss2=document.getElementById('fourd-cam-sttxt');
      fetch('/camera/'+figId,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(e.data.camera)
      }).then(function(r){
        if(_ss2){
          if(r.ok){_ss2.textContent='\u2713 Camera saved \u2014 click \u201cRebuild HTML\u201d to apply';_ss2.style.color='#4caf50';}
          else{_ss2.textContent='\u2717 Save failed (server error)';_ss2.style.color='#f44336';}
        }
        var ack={type:'4dpaper-camera-ack',fig_id:figId,status:r.ok?'ok':'error'};
        if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(ack,'*');
        if(e.source&&e.source!==(_f2&&_f2.contentWindow))e.source.postMessage(ack,'*');
      }).catch(function(){
        if(_ss2){_ss2.textContent='\u2717 Save failed (network error)';_ss2.style.color='#f44336';}
        var ack={type:'4dpaper-camera-ack',fig_id:figId,status:'error'};
        if(_f2&&_f2.contentWindow)_f2.contentWindow.postMessage(ack,'*');
        if(e.source&&e.source!==(_f2&&_f2.contentWindow))e.source.postMessage(ack,'*');
      });
```

Then before the closing `}` of `window.addEventListener` (currently line 128–129 `  });`), insert:
```
    } else if(e.data.type==="4dpaper-lock-query"){
      var lockFigId=e.data.fig_id;
      fetch("/camera-lock/"+lockFigId)
        .then(function(r){return r.json();})
        .then(function(d){
          if(e.source)e.source.postMessage(
            {type:"4dpaper-lock-state",fig_id:lockFigId,locked:!!d.locked},"*");
        }).catch(function(){
          if(e.source)e.source.postMessage(
            {type:"4dpaper-lock-state",fig_id:lockFigId,locked:false},"*");
        });
    } else if(e.data.type==="4dpaper-lock-toggle"){
      var lockFigId2=e.data.fig_id;
      fetch("/camera-lock/"+lockFigId2,{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({locked:!!e.data.locked})
      }).then(function(r){
        if(e.source)e.source.postMessage(
          {type:"4dpaper-lock-ack",fig_id:lockFigId2,status:r.ok?"ok":"error"},"*");
      }).catch(function(){
        if(e.source)e.source.postMessage(
          {type:"4dpaper-lock-ack",fig_id:lockFigId2,status:"error"},"*");
      });
    }
```

Note: the `} else if(e.data.type==="4dpaper-field-update"){` block (lines 118-127) stays unchanged between the camera block and the new lock blocks.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_camera_lock.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add _extensions/4dpaper/shortcodes.lua tests/test_camera_lock.py
git commit -m "feat: fix camera ack routing and add lock relay handlers"
```

---

## Task 4: Snippet additions for panel sync — `camera-apply` listener + wildcard ack filter

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py` (`_camera_sync_snippet`, lines already rewritten in Task 2)
- Create: `tests/test_panel_sync.py`

The `_camera_sync_snippet` needs two more additions for sync panels:
1. The ack filter already handles `"*"` (done in Task 2 — the `fig_id!==FIG_ID&&fig_id!=="*"` check is in the rewritten listener).
2. A `4dpaper-camera-apply` listener inside `waitRenderer` (so sync panel can rotate all cells simultaneously).

**Check first:** if the Task 2 snippet already includes the `fig_id!=="*"` ack filter, skip step 3a.

- [ ] **Step 1: Write tests**

Create `tests/test_panel_sync.py`:

```python
"""Tests for panel camera sync mode."""
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


class TestSnippetForSync:
    def test_wildcard_ack_accepted(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        # The ack filter must accept wildcard "*" from sync panels
        assert 'fig_id!=="*"' in snippet or "fig_id !== \"*\"" in snippet

    def test_camera_apply_listener_present(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        assert "4dpaper-camera-apply" in snippet

    def test_camera_apply_sets_camera_position(self):
        mod = _load_4dpaper()
        snippet = mod._camera_sync_snippet("fig-vm")
        assert "setPosition" in snippet
        assert "setFocalPoint" in snippet
        assert "setViewUp" in snippet
```

- [ ] **Step 2: Run tests**

```bash
python -m pytest tests/test_panel_sync.py::TestSnippetForSync -v
```

- [ ] **Step 3: If `4dpaper-camera-apply` listener is missing, add it inside `waitRenderer`**

In `_camera_sync_snippet`, the `waitRenderer(function(renderer){...})` block currently ends at:
```python
        f'    document.addEventListener("touchend",function(){{sendCamera(renderer);}});\n'
        f'  }});\n'
```

Add the camera-apply listener inside that callback, before the closing `}});\n`:

```python
        # Apply camera broadcast from sync panel (no pointerup fired, so sendCamera not called)
        f'    window.addEventListener("message",function(e){{\n'
        f'      if(!e.data||e.data.type!=="4dpaper-camera-apply")return;\n'
        f'      var cam=e.data.camera;\n'
        f'      if(!cam)return;\n'
        f'      var c=renderer.getActiveCamera();\n'
        f'      if(cam.position)c.setPosition(cam.position[0],cam.position[1],cam.position[2]);\n'
        f'      if(cam.focal_point)c.setFocalPoint(cam.focal_point[0],cam.focal_point[1],cam.focal_point[2]);\n'
        f'      if(cam.view_up)c.setViewUp(cam.view_up[0],cam.view_up[1],cam.view_up[2]);\n'
        f'      if(cam.parallel_scale!=null)c.setParallelScale(cam.parallel_scale);\n'
        f'      if(cam.parallel_projection!=null)c.setParallelProjection(!!cam.parallel_projection);\n'
        f'      window.renderWindow.render();\n'
        f'    }});\n'
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_panel_sync.py::TestSnippetForSync -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_panel_sync.py
git commit -m "feat: add camera-apply listener for sync panel rotation broadcast"
```

---

## Task 5: `parse_panel_shortcodes` and `generate_panel_html` — add `camera_mode`

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py:92-137` (`parse_panel_shortcodes`), `1237-1311` (`generate_panel_html`)

`parse_panel_shortcodes` gets a new `camera_mode` key. `generate_panel_html` branches on it: sync gets the new sync re_relay, independent gets the existing re_relay extended with lock pass-through.

- [ ] **Step 1: Write tests in `tests/test_panel_sync.py`**

Append to the file:

```python
class TestParsePanelShortcodes:
    def test_camera_mode_defaults_to_independent(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p1" layout="2x1" src1="a.foam" id1="f1" field1="Vm" src2="b.foam" id2="f2" field2="Vm" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["camera_mode"] == "independent"

    def test_camera_mode_sync_parsed(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p1" layout="2x1" camera="sync" src1="a.foam" id1="f1" field1="Vm" src2="b.foam" id2="f2" field2="Vm" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["camera_mode"] == "sync"

    def test_unknown_camera_value_treated_as_independent(self):
        mod = _load_4dpaper()
        text = '{{< 4d-panel id="p1" layout="1x1" camera="wibble" src1="a.foam" id1="f1" field1="Vm" >}}'
        result = mod.parse_panel_shortcodes(text)
        # Any non-"sync" value keeps "wibble" but generate_panel_html treats non-"sync" as independent
        assert "camera_mode" in result[0]


class TestGeneratePanelHtml:
    def test_sync_re_relay_contains_panel_id(self, tmp_path):
        """Sync composite HTML must contain PANEL_ID variable."""
        mod = _load_4dpaper()
        panel = {
            "id": "panel-vm",
            "layout": "2x1",
            "height": "400px",
            "caption": "",
            "camera_mode": "sync",
            "subfigures": [],
        }
        # generate_panel_html calls generate_html_figure for each subfigure — with no subfigures
        # it still writes the composite. We just check the re_relay script content.
        import inspect
        source = inspect.getsource(mod.generate_panel_html)
        assert "camera_mode" in source
        assert "PANEL_ID" in source

    def test_sync_re_relay_contains_camera_apply_broadcast(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "4dpaper-camera-apply" in source

    def test_independent_re_relay_has_lock_passthrough(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_html)
        assert "4dpaper-lock-query" in source
        assert "4dpaper-lock-state" in source
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_panel_sync.py::TestParsePanelShortcodes tests/test_panel_sync.py::TestGeneratePanelHtml -v
```

- [ ] **Step 3: Add `camera_mode` to `parse_panel_shortcodes`**

In `_extensions/4dpaper/4dpaper.py`, find `parse_panel_shortcodes` result dict (line 130):

```python
        results.append({
            "id":         kwargs["id"],
            "layout":     kwargs.get("layout", "1x1"),
            "height":     kwargs.get("height", "800px"),
            "caption":    kwargs.get("caption", ""),
            "subfigures": subfigures,
        })
```

Add `camera_mode`:

```python
        results.append({
            "id":          kwargs["id"],
            "layout":      kwargs.get("layout", "1x1"),
            "height":      kwargs.get("height", "800px"),
            "caption":     kwargs.get("caption", ""),
            "camera_mode": kwargs.get("camera", "independent"),
            "subfigures":  subfigures,
        })
```

- [ ] **Step 4: Update `generate_panel_html` to branch on `camera_mode`**

In `generate_panel_html`, find the `re_relay` assignment (lines 1271–1283) and replace with a conditional that produces different re_relay strings based on `panel.get("camera_mode", "independent")`. Immediately above the `re_relay = """..."""` line, change:

```python
    # Bidirectional re-relay: forwards camera/field UP to top, acks DOWN to children
    re_relay = """\
<script>
window.addEventListener("message",function(e){
  if(!e.data)return;
  if(e.data.type==="4dpaper-camera"||e.data.type==="4dpaper-field-update"){
    top.postMessage(e.data,"*");
  }
  if(e.data.type==="4dpaper-camera-ack"||e.data.type==="4dpaper-field-ack"){
    var iframes=document.querySelectorAll("iframe");
    for(var i=0;i<iframes.length;i++){iframes[i].contentWindow.postMessage(e.data,"*");}
  }
});
</script>"""
```

Replace with:

```python
    camera_mode = panel.get("camera_mode", "independent")
    panel_id = panel["id"]

    if camera_mode == "sync":
        re_relay = f"""\
<script>
var PANEL_ID="{panel_id}";
window.addEventListener("message",function(e){{
  if(!e.data)return;
  if(e.data.type==="4dpaper-camera"){{
    var msg=Object.assign({{}},e.data,{{fig_id:PANEL_ID}});
    top.postMessage(msg,"*");
    var iframes=document.querySelectorAll("iframe");
    for(var i=0;i<iframes.length;i++){{
      iframes[i].contentWindow.postMessage({{type:"4dpaper-camera-apply",camera:e.data.camera}},"*");
    }}
  }}
  if(e.data.type==="4dpaper-camera-ack"){{
    var camAck=Object.assign({{}},e.data,{{fig_id:"*"}});
    var iframes2=document.querySelectorAll("iframe");
    for(var j=0;j<iframes2.length;j++){{iframes2[j].contentWindow.postMessage(camAck,"*");}}
  }}
  if(e.data.type==="4dpaper-field-ack"){{
    var iframes3=document.querySelectorAll("iframe");
    for(var k=0;k<iframes3.length;k++){{iframes3[k].contentWindow.postMessage(e.data,"*");}}
  }}
  if(e.data.type==="4dpaper-field-update"){{top.postMessage(e.data,"*");}}
  if(e.data.type==="4dpaper-lock-query"||e.data.type==="4dpaper-lock-toggle"){{
    top.postMessage(e.data,"*");
  }}
  if(e.data.type==="4dpaper-lock-state"||e.data.type==="4dpaper-lock-ack"){{
    var iframes4=document.querySelectorAll("iframe");
    for(var l=0;l<iframes4.length;l++){{iframes4[l].contentWindow.postMessage(e.data,"*");}}
  }}
}});
</script>"""
    else:
        re_relay = """\
<script>
window.addEventListener("message",function(e){
  if(!e.data)return;
  if(e.data.type==="4dpaper-camera"||e.data.type==="4dpaper-field-update"){
    top.postMessage(e.data,"*");
  }
  if(e.data.type==="4dpaper-camera-ack"||e.data.type==="4dpaper-field-ack"){
    var iframes=document.querySelectorAll("iframe");
    for(var i=0;i<iframes.length;i++){iframes[i].contentWindow.postMessage(e.data,"*");}
  }
  if(e.data.type==="4dpaper-lock-query"||e.data.type==="4dpaper-lock-toggle"){
    top.postMessage(e.data,"*");
  }
  if(e.data.type==="4dpaper-lock-state"||e.data.type==="4dpaper-lock-ack"){
    var iframes2=document.querySelectorAll("iframe");
    for(var k=0;k<iframes2.length;k++){iframes2[k].contentWindow.postMessage(e.data,"*");}
  }
});
</script>"""
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_panel_sync.py::TestParsePanelShortcodes tests/test_panel_sync.py::TestGeneratePanelHtml -v
```

Expected: all PASS.

- [ ] **Step 6: Run full test suite for regressions**

```bash
python -m pytest tests/ -v --ignore=tests/test_data_loader.py 2>&1 | tail -20
```

Expected: all PASS (data_loader test skipped as it needs real simulation data).

- [ ] **Step 7: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_panel_sync.py
git commit -m "feat: add camera_mode to parse_panel_shortcodes and sync re_relay to generate_panel_html"
```

---

## Task 6: `generate_png_figure` — `camera_fig_id` param + `generate_panel_png` sync camera routing

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py:847-915` (`generate_png_figure`), `1314-1356` (`generate_panel_png`)

`generate_png_figure` gets a new `camera_fig_id` kwarg that overrides the camera lookup path. `generate_panel_png` reads `camera_mode` and passes the panel ID as `camera_fig_id` for sync panels.

- [ ] **Step 1: Add tests to `tests/test_panel_sync.py`**

Append:

```python
class TestGeneratePngFigureCameraFigId:
    def test_camera_fig_id_param_exists(self):
        import inspect
        mod = _load_4dpaper()
        sig = inspect.signature(mod.generate_png_figure)
        assert "camera_fig_id" in sig.parameters
        assert sig.parameters["camera_fig_id"].default is None

    def test_camera_fig_id_used_in_lookup(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_png_figure)
        assert "camera_fig_id" in source
        assert "_cam_id" in source


class TestGeneratePanelPngSyncCamera:
    def test_sync_mode_uses_panel_id_for_camera(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.generate_panel_png)
        assert "camera_mode" in source
        assert "camera_fig_id" in source
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_panel_sync.py::TestGeneratePngFigureCameraFigId -v
```

- [ ] **Step 3: Add `camera_fig_id` to `generate_png_figure`**

Change the signature (line 847):

```python
def generate_png_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
    camera_fig_id: str | None = None,
    background: str = "white",
    axis_color: str = "black",
    cmap: str = "coolwarm",
) -> None:
```

Change the camera lookup (line 910):

```python
    _cam_id = camera_fig_id or fig_id
    camera_path = (_project_root / "state" / f"camera_{_cam_id}.json" if _cam_id else None)
    apply_camera_state(pl, _cam_id or "unnamed", camera_path)
```

(The existing line `apply_camera_state(pl, fig_id or "unnamed", camera_path)` passes `fig_id` — change the second argument to `_cam_id or "unnamed"` as well.)

- [ ] **Step 4: Update `generate_panel_png` to pass `camera_fig_id`**

In `generate_panel_png`, find the subfigure loop (line 1341–1344):

```python
    # Generate each sub-figure PNG (reuses caching inside generate_png_figure)
    for sub in panel["subfigures"]:
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        out = figures_dir / f"{sub['id']}.png"
        generate_png_figure(src, sub["field"], sub["time"], out, fig_id=sub["id"])
```

Replace with:

```python
    camera_mode = panel.get("camera_mode", "independent")
    # Generate each sub-figure PNG
    for sub in panel["subfigures"]:
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        out = figures_dir / f"{sub['id']}.png"
        cam_id = panel["id"] if camera_mode == "sync" else sub["id"]
        generate_png_figure(src, sub["field"], sub["time"], out,
                            fig_id=sub["id"], camera_fig_id=cam_id)
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_panel_sync.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py
git commit -m "feat: add camera_fig_id param to generate_png_figure; sync panels use panel-level camera"
```

---

## Task 7: `main()` — sync-aware panel cache invalidation

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py:1738-1777` (panel processing loop in `main()`)

For sync panels, replace the per-subfigure camera dep check with a single panel-level camera file check.

- [ ] **Step 1: Add test to `tests/test_panel_sync.py`**

Append:

```python
class TestSyncPanelCacheInvalidation:
    def test_main_source_uses_panel_camera_for_sync(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        # The panel loop must branch on camera_mode for sync
        assert "camera_mode" in source
        assert "shared_cam" in source
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
python -m pytest tests/test_panel_sync.py::TestSyncPanelCacheInvalidation -v
```

- [ ] **Step 3: Update the panel cache loop in `main()`**

Find the panel processing loop at line 1738. The current `sub_mtimes` block (lines 1743–1757) collects all subfigure camera JSONs without distinguishing sync vs. independent. Replace lines 1738–1757:

```python
    for panel in panels:
        panel_id = panel["id"]
        camera_mode = panel.get("camera_mode", "independent")
        out_html = figures_dir / f"{panel_id}.html"
        out_png  = figures_dir / f"{panel_id}.png"

        # Determine max mtime of all sub-figure source files and camera deps
        sub_mtimes = []
        for sub in panel["subfigures"]:
            src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
            if src.exists():
                sub_mtimes.append(src.stat().st_mtime)
        # Camera deps: sync panels use one shared file; independent use per-subfigure files
        if camera_mode == "sync":
            shared_cam = _project_root / "state" / f"camera_{panel_id}.json"
            if shared_cam.exists():
                sub_mtimes.append(shared_cam.stat().st_mtime)
        else:
            for sub in panel["subfigures"]:
                cam = _project_root / "state" / f"camera_{sub['id']}.json"
                if cam.exists():
                    sub_mtimes.append(cam.stat().st_mtime)
        script_mtime = _here.stat().st_mtime
        sub_mtimes.append(script_mtime)
        for qmd in qmd_files:
            if qmd.exists():
                sub_mtimes.append(qmd.stat().st_mtime)
        max_dep_mtime = max(sub_mtimes) if sub_mtimes else 0.0
```

The rest of the loop (lines 1759–1777 — the `if out_html.exists()` and `if out_png.exists()` checks) stays exactly the same.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_panel_sync.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py
git commit -m "feat: sync panels use panel-level camera JSON for cache invalidation"
```

---

## Task 8: `fourd_panel` Lua — sync branch

**Files:**
- Modify: `_extensions/4dpaper/shortcodes.lua:300-403` (`fourd_panel`)

Add `camera_mode` kwarg parsing. When `camera_mode == "sync"`, embed the composite HTML as a single iframe. The independent branch keeps the existing behaviour.

- [ ] **Step 1: Add test to `tests/test_panel_sync.py`**

Append:

```python
class TestFourdPanelLua:
    def test_fourd_panel_reads_camera_kwarg(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'kwargs["camera"]' in content

    def test_fourd_panel_has_sync_branch(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'camera_mode == "sync"' in content

    def test_fourd_panel_sync_embeds_composite_html(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        # The sync branch reads the composite HTML file (not individual subfigure files)
        assert 'state/figures/" .. id .. ".html"' in content
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_panel_sync.py::TestFourdPanelLua -v
```

- [ ] **Step 3: Update `fourd_panel` in `shortcodes.lua`**

Replace the function signature and the HTML branch in `fourd_panel`. The current function (lines 300–403) starts with:

```lua
local function fourd_panel(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))
  local height  = pandoc.utils.stringify(kwargs["height"]  or pandoc.Str("800px"))
  local layout  = pandoc.utils.stringify(kwargs["layout"]  or pandoc.Str("1x1"))
```

Replace the first four local declarations with:

```lua
local function fourd_panel(args, kwargs)
  local id          = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption     = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))
  local height      = pandoc.utils.stringify(kwargs["height"]  or pandoc.Str("800px"))
  local layout      = pandoc.utils.stringify(kwargs["layout"]  or pandoc.Str("1x1"))
  local camera_mode = pandoc.utils.stringify(kwargs["camera"]  or pandoc.Str("independent"))
```

Then inside `if quarto.doc.isFormat("html") then`, insert the sync branch **before** the existing independent-mode code (before `local ncols = tonumber...`):

```lua
  if quarto.doc.isFormat("html") then
    -- Inject relay script once per page
    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end

    if camera_mode == "sync" then
      -- Sync mode: embed composite HTML as single iframe so sync re_relay executes.
      local composite_path = "state/figures/" .. id .. ".html"
      local f = io.open(composite_path, "r")
      if not f then
        return pandoc.RawBlock("html",
          '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
          '⚠ 4D Panel <code>' .. id .. '</code> not yet rendered — ' ..
          'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
      end
      local composite_iframe
      if _app_mode then
        f:close()
        composite_iframe = '<iframe src="/state/figures/' .. id .. '.html" ' ..
                           'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
      else
        local content = f:read("*all"); f:close()
        local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
        composite_iframe = '<iframe srcdoc="' .. escaped .. '" ' ..
                           'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
      end
      return pandoc.RawBlock("html",
        '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
        composite_iframe .. '\n' ..
        (caption ~= "" and
          '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
          or "") ..
        '</figure>\n' .. relay_script)
    end

    -- Independent mode: existing inline-subfigure grid below
    local ncols = tonumber(layout:match("^(%d+)x")) or 1
```

- [ ] **Step 3b: Remove the duplicate relay-injection block from the existing independent-mode code**

The existing `fourd_panel` independent-mode code (lines 371–376) has its own relay injection guard:
```lua
    -- Inject relay script once per page (shared guard with fourd_image/fourd_video)
    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end
```

This block now appears at the top of the HTML branch (before the sync/independent split), so it must be **removed** from the independent-mode section to avoid a double-set of `_relay_injected` and double relay injection. Delete those 6 lines from the independent-mode code. The independent branch's `return pandoc.RawBlock(...)` call still uses `relay_script` (which was set in the shared block above).

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_panel_sync.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add _extensions/4dpaper/shortcodes.lua tests/test_panel_sync.py
git commit -m "feat: fourd_panel sync branch embeds composite HTML as single iframe"
```

---

## Task 9: Timeseries Python — `parse_timeseries_shortcodes`, `_expand_timeseries_steps`, `main()` wiring

**Files:**
- Modify: `_extensions/4dpaper/4dpaper.py`
- Create: `tests/test_timeseries.py`

`parse_timeseries_shortcodes` returns raw dicts; `_expand_timeseries_steps` converts `steps`/`times` to a list of integer indices; `main()` collects timeseries, expands them, and merges into `panels`.

- [ ] **Step 1: Write tests**

Create `tests/test_timeseries.py`:

```python
"""Tests for 4d-timeseries shortcode parsing and step expansion."""
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


class TestParseTimeseriesShortcodes:
    def test_basic_parse(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="case.foam" field="Vm" id="ts-vm" steps="4" caption="My cap" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert len(result) == 1
        r = result[0]
        assert r["id"] == "ts-vm"
        assert r["src"] == "case.foam"
        assert r["field"] == "Vm"
        assert r["steps"] == "4"
        assert r["caption"] == "My cap"
        assert r["camera_mode"] == "sync"
        assert r["timeseries"] is True

    def test_times_param_parsed(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="c.foam" field="Vm" id="ts1" times="first,5,last" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert result[0]["times"] == "first,5,last"

    def test_missing_id_skipped(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="c.foam" field="Vm" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert result == []

    def test_default_steps_is_four(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="c.foam" field="Vm" id="ts1" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert result[0]["steps"] == "4"

    def test_subfigures_initially_empty(self):
        mod = _load_4dpaper()
        text = '{{< 4d-timeseries src="c.foam" field="Vm" id="ts1" >}}'
        result = mod.parse_timeseries_shortcodes(text)
        assert result[0]["subfigures"] == []
        assert result[0]["layout"] is None


class TestExpandTimeseriesSteps:
    def test_steps_4_divides_evenly(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": ""}
        result = mod._expand_timeseries_steps(ts, 100)
        assert len(result) == 4
        assert result[0] == 0
        assert result[-1] == 99

    def test_times_first_and_last(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": "first,last"}
        result = mod._expand_timeseries_steps(ts, 50)
        assert result == [0, 49]

    def test_times_explicit_indices(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": "0,5,10"}
        result = mod._expand_timeseries_steps(ts, 20)
        assert result == [0, 5, 10]

    def test_times_clamps_to_max(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": "0,999"}
        result = mod._expand_timeseries_steps(ts, 10)
        assert result[1] == 9  # clamped to n_steps - 1

    def test_times_invalid_falls_back_to_steps(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "3", "times": "abc,xyz"}
        result = mod._expand_timeseries_steps(ts, 10)
        assert len(result) == 3  # falls back to steps=3

    def test_steps_1_treated_as_2(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "1", "times": ""}
        result = mod._expand_timeseries_steps(ts, 10)
        assert len(result) == 2  # max(2, 1) = 2

    def test_n_steps_1_returns_single_frame(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": ""}
        result = mod._expand_timeseries_steps(ts, 1)
        assert result == [0]

    def test_n_steps_0_returns_single_frame(self):
        mod = _load_4dpaper()
        ts = {"id": "ts1", "steps": "4", "times": ""}
        result = mod._expand_timeseries_steps(ts, 0)
        assert result == [0]


class TestMainTimeseriesIntegration:
    def test_main_source_has_parse_timeseries(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        assert "parse_timeseries_shortcodes" in source
        assert "ts_raw" in source

    def test_main_guard_includes_ts_raw(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        # The early-exit guard must check ts_raw too
        assert "ts_raw" in source

    def test_main_merges_timeseries_into_panels(self):
        import inspect
        mod = _load_4dpaper()
        source = inspect.getsource(mod.main)
        assert "panels.append(ts)" in source
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_timeseries.py -v 2>&1 | head -30
```

Expected: `AttributeError` — `parse_timeseries_shortcodes` and `_expand_timeseries_steps` don't exist yet.

- [ ] **Step 3: Add `parse_timeseries_shortcodes` to `4dpaper.py`**

Add after `parse_panel_shortcodes` (after line 137), before the PVSM section:

```python
def parse_timeseries_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-timeseries key="value" ... >}} shortcodes from QMD text.

    Returns raw dicts — step expansion happens in main() after simulation load.
    Shortcodes missing 'id' or 'src' are skipped.
    """
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-timeseries\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs:
            print("[4dpaper] Warning: 4d-timeseries shortcode missing 'id' — skipping.", file=sys.stderr)
            continue
        if "src" not in kwargs:
            print("[4dpaper] Warning: 4d-timeseries shortcode missing 'src' — skipping.", file=sys.stderr)
            continue
        results.append({
            "id":         kwargs["id"],
            "layout":     None,
            "height":     kwargs.get("height", "400px"),
            "caption":    kwargs.get("caption", ""),
            "camera_mode": "sync",
            "timeseries": True,
            "src":        kwargs["src"],
            "field":      kwargs.get("field", ""),
            "steps":      kwargs.get("steps", "4"),
            "times":      kwargs.get("times", ""),
            "subfigures": [],
        })
    return results
```

- [ ] **Step 4: Add `_expand_timeseries_steps` to `4dpaper.py`**

Add after `parse_timeseries_shortcodes` (before the PVSM section):

```python
def _expand_timeseries_steps(ts: dict, n_steps: int) -> list[int]:
    """Expand steps/times string to list of integer step indices.

    times= takes precedence. If all tokens are invalid, falls back to steps= logic.
    n_steps <= 1 yields [0] with a warning (degenerate single-frame case).
    steps="1" is treated as steps="2" (minimum useful timeseries).
    """
    if ts["times"]:
        result = []
        for tok in ts["times"].split(","):
            tok = tok.strip()
            if tok == "first":
                result.append(0)
            elif tok == "last":
                result.append(max(0, n_steps - 1))
            else:
                try:
                    result.append(max(0, min(int(tok), n_steps - 1)))
                except ValueError:
                    pass  # skip invalid tokens
        if result:
            return result
        # All tokens invalid — fall through to steps= logic
    if n_steps <= 1:
        print(
            f"[4dpaper] WARNING: timeseries '{ts['id']}' source has only {n_steps} step(s) "
            "— generating single frame.", file=sys.stderr
        )
        return [0]
    N = max(2, int(ts.get("steps", "4")))
    return [round(i * (n_steps - 1) / (N - 1)) for i in range(N)]
```

- [ ] **Step 5: Update `main()` — add timeseries collection, early-exit guard update, and expansion loop**

In `main()`, find the shortcode collection block (lines 1583–1596):

```python
    figures = []
    videos = []
    panels = []
    pvsm_figs = []
    for qmd in qmd_files:
        text = qmd.read_text()
        figures.extend(parse_shortcodes(text))
        videos.extend(parse_video_shortcodes(text))
        panels.extend(parse_panel_shortcodes(text))
        pvsm_figs.extend(parse_pvsm_shortcodes(text))

    if not figures and not videos and not panels and not pvsm_figs:
        print("[4dpaper] No 4d-image, 4d-video, 4d-panel, or 4d-pvsm shortcodes found.", file=sys.stderr)
        return
```

Replace with:

```python
    figures = []
    videos = []
    panels = []
    pvsm_figs = []
    ts_raw = []
    for qmd in qmd_files:
        text = qmd.read_text()
        figures.extend(parse_shortcodes(text))
        videos.extend(parse_video_shortcodes(text))
        panels.extend(parse_panel_shortcodes(text))
        pvsm_figs.extend(parse_pvsm_shortcodes(text))
        ts_raw.extend(parse_timeseries_shortcodes(text))

    if not any([figures, videos, panels, pvsm_figs, ts_raw]):
        print("[4dpaper] No 4d-image, 4d-video, 4d-panel, 4d-pvsm, or 4d-timeseries shortcodes found.", file=sys.stderr)
        return
```

Then, after the `figures_dir.mkdir(...)` line (line 1598) and after the styles block, add the timeseries expansion loop. Find `# Load style templates once` block (lines 1601–1604). After the styles block, before the `for fig in figures:` loop, insert:

```python
    # Expand timeseries into panel-compatible dicts and merge into panels list
    from scripts.data_loader import SimulationData as _SimData
    for ts in ts_raw:
        src = Path(ts["src"]) if Path(ts["src"]).is_absolute() else _project_root / ts["src"]
        try:
            sim = _SimData(str(src)).load()
            n_steps = sim.n_steps
        except Exception as exc:
            print(f"[4dpaper] ERROR loading simulation for timeseries '{ts['id']}': {exc}", file=sys.stderr)
            sys.exit(1)
        step_indices = _expand_timeseries_steps(ts, n_steps)
        ts["subfigures"] = [
            {
                "src":    ts["src"],
                "id":     f"{ts['id']}-{i}",
                "field":  ts["field"],
                "time":   str(idx),
                "fields": "",
            }
            for i, idx in enumerate(step_indices)
        ]
        ts["layout"] = f"{len(step_indices)}x1"
        panels.append(ts)
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_timeseries.py -v
```

Expected: all PASS.

- [ ] **Step 7: Run full suite**

```bash
python -m pytest tests/ -v --ignore=tests/test_data_loader.py 2>&1 | tail -20
```

- [ ] **Step 8: Commit**

```bash
git add _extensions/4dpaper/4dpaper.py tests/test_timeseries.py
git commit -m "feat: add parse_timeseries_shortcodes, _expand_timeseries_steps, and main() wiring"
```

---

## Task 10: `fourd_timeseries` Lua handler

**Files:**
- Modify: `_extensions/4dpaper/shortcodes.lua:501-506` (return table)
- Add new `fourd_timeseries` function before the `return` block

The Lua handler embeds the Python-generated composite HTML (`state/figures/<id>.html`) as a single iframe (always sync mode). For PDF, it embeds `state/figures/<id>.png`.

- [ ] **Step 1: Add tests to `tests/test_timeseries.py`**

Append:

```python
class TestFourdTimeseriesLua:
    def test_fourd_timeseries_function_exists(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert "fourd_timeseries" in content

    def test_fourd_timeseries_registered(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert '["4d-timeseries"]' in content

    def test_fourd_timeseries_embeds_composite_html(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        # Must probe the composite (not individual subfigure files)
        assert 'state/figures/" .. id .. ".html"' in content

    def test_fourd_timeseries_pdf_uses_90_percent_width(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        # Must use 90% width like fourd_panel for consistency
        # Count occurrences of width = "90%" — timeseries must be one of them
        assert 'width = "90%"' in content
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_timeseries.py::TestFourdTimeseriesLua -v
```

- [ ] **Step 3: Add `fourd_timeseries` to `shortcodes.lua`**

Insert before `return {` (line 501):

```lua
local function fourd_timeseries(args, kwargs)
  local id      = pandoc.utils.stringify(kwargs["id"]      or pandoc.Str(""))
  local caption = pandoc.utils.stringify(kwargs["caption"] or pandoc.Str(""))
  local height  = pandoc.utils.stringify(kwargs["height"]  or pandoc.Str("400px"))

  if id == "" then
    return pandoc.RawBlock("html",
      '<div style="color:red">⚠ 4d-timeseries: missing required attribute <code>id</code></div>')
  end

  if quarto.doc.isFormat("html") then
    -- Timeseries is always sync — embed the Python-generated composite HTML as one iframe.
    local composite_path = "state/figures/" .. id .. ".html"
    local f = io.open(composite_path, "r")

    if not f then
      return pandoc.RawBlock("html",
        '<div style="border:2px dashed #888;padding:1.5rem;text-align:center;">' ..
        '⚠ 4D Timeseries <code>' .. id .. '</code> not yet rendered — ' ..
        'click <strong>Rebuild HTML</strong> in the dashboard.</div>')
    end

    local composite_iframe
    if _app_mode then
      f:close()
      composite_iframe = '<iframe src="/state/figures/' .. id .. '.html" ' ..
                         'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
    else
      local content = f:read("*all"); f:close()
      local escaped = content:gsub("&", "&amp;"):gsub('"', "&quot;")
      composite_iframe = '<iframe srcdoc="' .. escaped .. '" ' ..
                         'style="width:100%;height:' .. height .. ';border:none;" frameborder="0"></iframe>'
    end

    local relay_script = ""
    if not _relay_injected then
      _relay_injected = true
      relay_script = _RELAY_SCRIPT
    end
    return pandoc.RawBlock("html",
      '<figure class="fourd-figure" style="margin:1.5rem 0;">\n' ..
      composite_iframe .. '\n' ..
      (caption ~= "" and
        '<figcaption style="text-align:center;font-style:italic;margin-top:0.5rem;">' .. caption .. '</figcaption>\n'
        or "") ..
      '</figure>\n' .. relay_script)

  else
    -- PDF: single composite PNG at state/figures/<id>.png
    local fig_path = "state/figures/" .. id .. ".png"
    local f = io.open(fig_path, "r")
    if f then
      f:close()
      local img = pandoc.Image(caption, fig_path, id, pandoc.Attr(id, {}, {width = "90%"}))
      return pandoc.Para({img})
    else
      return pandoc.Para({
        pandoc.Str("[Timeseries "), pandoc.Code(id),
        pandoc.Str(" — run 'Export PDF' from the dashboard to generate this figure]"),
      })
    end
  end
end
```

Update `return {` to add the registration:

```lua
return {
  ["4d-image"]      = fourd_image,
  ["4d-video"]      = fourd_video,
  ["4d-panel"]      = fourd_panel,
  ["4d-pvsm"]       = fourd_pvsm,
  ["4d-timeseries"] = fourd_timeseries,
}
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_timeseries.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v --ignore=tests/test_data_loader.py 2>&1 | tail -30
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add _extensions/4dpaper/shortcodes.lua tests/test_timeseries.py
git commit -m "feat: add fourd_timeseries Lua handler with composite-iframe approach"
```

---

## Final verification

- [ ] **Run the full test suite one more time**

```bash
python -m pytest tests/ -v --ignore=tests/test_data_loader.py
```

Expected: all PASS, no regressions in `test_extension.py`, `test_styles.py`, `test_camera_plugin.py`.

- [ ] **Check no placeholder strings remain**

```bash
grep -rn "TODO\|FIXME\|PLACEHOLDER\|\.\.\." _extensions/4dpaper/4dpaper.py dashboard/camera_plugin.py _extensions/4dpaper/shortcodes.lua | grep -v "^Binary" | grep -v "\.pyc"
```

- [ ] **Final commit if needed**

```bash
git add -p
git commit -m "feat: complete camera lock, panel sync, and timeseries implementation"
```
