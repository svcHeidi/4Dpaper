#!/usr/bin/env python3
"""
4DPaper pre-render hook — run by Quarto before rendering.

Scans the .qmd for {{< 4d-image >}} shortcodes and generates
figure files in state/figures/ (HTML for web, PNG for PDF).

Quarto calls this script before rendering. It reads QUARTO_DOCUMENT_PATH
and QUARTO_OUTPUT_FORMAT from the environment.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# ── Ensure venv Python is used ────────────────────────────────────────────────
_here = Path(__file__).resolve()
_project_root = _here.parent.parent.parent  # _extensions/4dpaper/ → project root
_venv_python = _project_root / ".venv" / "bin" / "python"
_under_pytest = "pytest" in sys.modules or any("pytest" in a for a in sys.argv)
if (
    _venv_python.exists()
    and not _under_pytest
    and Path(sys.executable).resolve() != _venv_python.resolve()
):
    os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

# Add project root to path for scripts/
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ── Shortcode parsing ─────────────────────────────────────────────────────────

def parse_video_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-video key="value" ... >}} shortcodes from QMD text.

    Returns a list of dicts with at minimum 'id', 'src', 'field' keys.
    Shortcodes missing 'id' or 'src' are silently skipped.
    'fps' defaults to '10', 'time' defaults to 'mid' if not specified.
    """
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-video\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("fps", "10")
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        results.append(kwargs)
    return results


def parse_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-image key="value" ... >}} shortcodes from QMD text.

    Returns a list of dicts with at minimum 'id', 'src', 'field' keys.
    Shortcodes missing 'id' or 'src' are silently skipped.
    'time' defaults to 'mid' if not specified.
    """
    # Strip fenced code blocks (``` ... ```) before scanning for shortcodes
    # so that shortcodes shown as examples in code blocks are not processed.
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)

    pattern = r'\{\{<\s*4d-image\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        kwargs.setdefault("fields", "")  # comma-separated list for live switching
        results.append(kwargs)
    return results


def parse_panel_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-panel key="value" ... >}} shortcodes from QMD text.

    Layout convention: "COLSxROWS" — columns first, rows second.
    E.g. "2x2" = 2 columns 2 rows, "3x1" = 3 columns 1 row.

    Sub-figures are numbered from 1: src1/id1/field1/time1, src2/id2/...
    Parser reads until src<n> is absent for the next n.

    Returns list of panel dicts; panels missing 'id' or sub-figures are skipped.
    """
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-panel\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs:
            print("[4dpaper] Warning: 4d-panel shortcode missing 'id' — skipping.", file=sys.stderr)
            continue
        # Collect numbered sub-figures
        subfigures = []
        n = 1
        while f"src{n}" in kwargs:
            subfigures.append({
                "src":   kwargs[f"src{n}"],
                "id":    kwargs.get(f"id{n}", f"panel-sub-{n}"),
                "field": kwargs.get(f"field{n}", ""),
                "time":  kwargs.get(f"time{n}", "mid"),
            })
            n += 1
        if not subfigures:
            print(f"[4dpaper] Warning: 4d-panel '{kwargs['id']}' has no sub-figures — skipping.", file=sys.stderr)
            continue
        results.append({
            "id":         kwargs["id"],
            "layout":     kwargs.get("layout", "1x1"),
            "height":     kwargs.get("height", "800px"),
            "caption":    kwargs.get("caption", ""),
            "subfigures": subfigures,
        })
    return results


# ── Cache helpers ─────────────────────────────────────────────────────────────

def is_cache_valid(
    fig_path: Path,
    src_path: Path,
    camera_path: Path | None = None,
    field_path: Path | None = None,
) -> bool:
    """
    Return True if fig_path exists, is newer than src_path, and is newer
    than camera_path (if given and present).

    Returns True (assume valid) if src_path does not exist.
    """
    if not fig_path.exists():
        return False
    fig_mtime = fig_path.stat().st_mtime
    if src_path.exists() and fig_mtime <= src_path.stat().st_mtime:
        return False
    if camera_path is not None and camera_path.exists():
        if fig_mtime <= camera_path.stat().st_mtime:
            return False
    if field_path is not None and field_path.exists():
        if fig_mtime <= field_path.stat().st_mtime:
            return False
    return True


# ── Camera orientation transfer ───────────────────────────────────────────────


def _apply_camera_from_dict(pl, fig_id: str, camera_data: dict | None) -> None:
    """
    Apply camera from a pre-loaded dict (avoids re-reading disk per frame).

    None or missing keys → isometric fallback. Mirrors apply_camera_state()
    but accepts a dict instead of a Path, for use in video render loops.
    """
    if camera_data is None:
        pl.isometric_view()
        return
    try:
        pl.camera.position = camera_data["position"]
        pl.camera.focal_point = camera_data["focal_point"]
        pl.camera.up = camera_data["view_up"]
        if "parallel_scale" in camera_data and camera_data["parallel_scale"] is not None:
            pl.camera.parallel_scale = float(camera_data["parallel_scale"])
        is_parallel = camera_data.get("parallel_projection", 0) == 1
        pl.camera.parallel_projection = is_parallel
    except (KeyError, ValueError):
        pl.isometric_view()


def apply_camera_state(pl, fig_id: str, camera_path: Path | None = None) -> None:
    """
    Apply saved camera state (from state/camera_<fig_id>.json) to a plotter.

    Handles position, focal point, view up, and parallel scale (zoom).
    If no camera state exists, falls back to a clean isometric view.
    """
    if camera_path is None or not camera_path.exists():
        pl.isometric_view()
        return

    try:
        cam_data = json.loads(camera_path.read_text())
        pl.camera.position = cam_data["position"]
        pl.camera.focal_point = cam_data["focal_point"]
        pl.camera.up = cam_data["view_up"]

        # Parallel scale is used for zooming in orthographic mode
        if "parallel_scale" in cam_data and cam_data["parallel_scale"] is not None:
            pl.camera.parallel_scale = float(cam_data["parallel_scale"])
            print(f"[4dpaper] Applied saved camera for {fig_id} (scale={pl.camera.parallel_scale:.4f})")
        else:
            print(f"[4dpaper] Applied saved camera for {fig_id}")

        # Ensure projection mode matches (perspective vs parallel/ortho)
        is_parallel = cam_data.get("parallel_projection", 0) == 1
        pl.camera.parallel_projection = is_parallel

    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"[4dpaper] Warning: could not apply camera for {fig_id}: {exc}. Falling back to isometric.")
        pl.isometric_view()


# ── Camera sync snippet ───────────────────────────────────────────────────────

def _camera_sync_snippet(fig_id: str) -> str:
    """
    Return an HTML+JS snippet that saves the vtk.js camera on every mouse/touch release.

    Uses parent.postMessage() to relay camera data from the srcdoc iframe
    (which has a null origin and cannot use fetch()) to the parent Quarto HTML
    page. A relay listener in the Quarto page (injected by shortcodes.lua)
    receives the message and calls fetch("/camera/<fig_id>") from the same
    origin as the Panel server.

    - Debounced 300 ms so rapid drags only send one request.
    - A brief green "📷 Camera synced" badge appears for 3 s on success, then hides.
    - A red "📷 Sync error" badge stays visible on failure.
    - Listens for "4dpaper-camera-ack" messages back from the parent to show badges.
    """
    fig_id_js = json.dumps(fig_id).replace("</", "<\\/")
    fig_id_safe = fig_id.replace("</", "<\\/")
    return (
        # Badge is hidden until a sync succeeds or fails
        f'<div id="camera-badge-{fig_id_safe}" style="position:fixed;top:8px;right:8px;'
        f'display:none;color:#fff;padding:4px 8px;'
        f'border-radius:4px;font-size:11px;font-family:monospace;'
        f'z-index:9999;pointer-events:none;"></div>\n'
        f'<script>\n'
        f'(function(){{\n'
        f'  var FIG_ID={fig_id_js};\n'
        f'  var badge=document.getElementById("camera-badge-{fig_id_safe}");\n'
        f'  var timer=null, hideTimer=null;\n'
        # Listen for acknowledgement messages from the parent relay
        f'  window.addEventListener("message",function(e){{\n'
        f'    if(!e.data||e.data.type!=="4dpaper-camera-ack")return;\n'
        f'    if(e.data.fig_id!==FIG_ID)return;\n'
        f'    if(e.data.status==="ok"){{\n'
        f'      badge.innerHTML="&#128247; Camera synced";\n'
        f'      badge.style.background="rgba(0,140,0,0.85)";\n'
        f'      badge.style.display="block";\n'
        f'      clearTimeout(hideTimer);\n'
        f'      hideTimer=setTimeout(function(){{badge.style.display="none";}},3000);\n'
        f'    }}else{{\n'
        f'      badge.innerHTML="&#128247; Sync error";\n'
        f'      badge.style.background="rgba(180,0,0,0.85)";\n'
        f'      badge.style.display="block";\n'
        f'    }}\n'
        f'  }});\n'
        f'  function sendCamera(renderer){{\n'
        f'    clearTimeout(timer);\n'
        f'    timer=setTimeout(function(){{\n'
        f'      var cam=renderer.getActiveCamera();\n'
        f'      parent.postMessage({{\n'
        f'        type:"4dpaper-camera",\n'
        f'        fig_id:FIG_ID,\n'
        f'        camera:{{\n'
        f'          position:cam.getPosition(),\n'
        f'          focal_point:cam.getFocalPoint(),\n'
        f'          view_up:cam.getViewUp(),\n'
        f'          parallel_scale:cam.getParallelScale(),\n'
        f'          parallel_projection:cam.getParallelProjection()?1:0\n'
        f'        }}\n'
        f'      }},"*");\n'
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
        # vtk.js uses Pointer Events API (pointerup), not legacy mouseup.
        # Listen to both to cover all browsers and interaction modes.
        f'    document.addEventListener("pointerup",function(){{sendCamera(renderer);}});\n'
        f'    document.addEventListener("mouseup",function(){{sendCamera(renderer);}});\n'
        f'    document.addEventListener("touchend",function(){{sendCamera(renderer);}});\n'
        f'  }});\n'
        f'}})();\n'
        f'</script>'
    )

def _field_sync_snippet(
    fig_id: str,
    available_fields: list[str],
    cur_field: str,
    field_data_b64: dict[str, str],
    field_ranges: dict[str, list[float]],
) -> str:
    """
    Return an HTML+JS snippet for live client-side field switching.

    Embeds all additional field arrays as base64 Float32Arrays. On select
    change, decodes the array and swaps the data in the vtk.js polydata in
    place — no page reload, no server round-trip needed for the visual update.

    Still fires a silent postMessage so the Dashboard relay can persist the
    selection to state/field_<fig_id>.json for PDF export (fire-and-forget;
    fails silently when no Dashboard is present).

    If only one field is available, renders a static label with no interaction.
    """
    if not available_fields:
        return ""

    fig_id_js = json.dumps(fig_id).replace("</", "<\\/")
    fig_id_safe = fig_id.replace("</", "<\\/").replace('"', '')

    # Build select options
    field_opts = "".join(
        f'<option value="{f}" {"selected" if f == cur_field else ""}>{f}</option>'
        for f in available_fields
    )

    # JS: embed all field data blobs and ranges
    field_data_js = json.dumps(field_data_b64).replace("</", "<\\/")
    field_ranges_js = json.dumps(field_ranges).replace("</", "<\\/")
    original_field_js = json.dumps(cur_field).replace("</", "<\\/")

    # Hide the switcher if there is only one field to choose from
    hide_if_single = "display:none;" if len(available_fields) <= 1 else ""

    return (
        f'<div style="position:fixed;bottom:8px;left:8px;z-index:9999;{hide_if_single}'
        f'background:rgba(30,30,30,0.85);'
        f'padding:8px;border-radius:6px;font-family:sans-serif;font-size:12px;color:#eee;'
        f'box-shadow:0 4px 12px rgba(0,0,0,0.5);display:flex;gap:8px;align-items:center;">\n'
        f'  <label>Field:\n'
        f'    <select id="field-sel-{fig_id_safe}"'
        f' style="background:#333;color:#fff;border:1px solid #555;border-radius:3px;">\n'
        f'      {field_opts}\n'
        f'    </select>\n'
        f'  </label>\n'
        f'  <span id="field-badge-{fig_id_safe}"'
        f' style="display:none;padding:2px 6px;border-radius:2px;font-size:11px;"></span>\n'
        f'</div>\n'
        f'<script>\n'
        f'(function(){{\n'
        f'  var FIG_ID={fig_id_js};\n'
        f'  var FIELD_DATA={field_data_js};\n'
        f'  var FIELD_RANGES={field_ranges_js};\n'
        f'  var ORIGINAL_FIELD={original_field_js};\n'
        f'  var fSel=document.getElementById("field-sel-{fig_id_safe}");\n'
        f'  var badge=document.getElementById("field-badge-{fig_id_safe}");\n'
        f'\n'
        f'  // Decode base64 string -> Float32Array\n'
        f'  function decodeField(b64){{\n'
        f'    var bin=atob(b64);\n'
        f'    var bytes=new Uint8Array(bin.length);\n'
        f'    for(var i=0;i<bin.length;i++)bytes[i]=bin.charCodeAt(i);\n'
        f'    return new Float32Array(bytes.buffer);\n'
        f'  }}\n'
        f'\n'
        f'  // Poll until the vtk.js mapper has the original field array loaded\n'
        f'  function waitMapper(cb){{\n'
        f'    function check(){{\n'
        f'      var rw=window.renderWindow;\n'
        f'      if(rw&&rw.getRenderers){{\n'
        f'        var renderers=rw.getRenderers();\n'
        f'        for(var i=0;i<renderers.length;i++){{\n'
        f'          var r=renderers[i];\n'
        f'          if(!r||!r.getActors)continue;\n'
        f'          var actors=r.getActors();\n'
        f'          for(var j=0;j<actors.length;j++){{\n'
        f'            var actor=actors[j];\n'
        f'            if(!actor||!actor.getMapper)continue;\n'
        f'            var mapper=actor.getMapper();\n'
        f'            if(!mapper||!mapper.getInputData)continue;\n'
        f'            var pd=mapper.getInputData();\n'
        f'            if(pd&&pd.getPointData&&pd.getPointData().getArrayByName(ORIGINAL_FIELD)){{\n'
        f'              cb(mapper,r);return;\n'
        f'            }}\n'
        f'          }}\n'
        f'        }}\n'
        f'      }}\n'
        f'      setTimeout(check,200);\n'
        f'    }}\n'
        f'    check();\n'
        f'  }}\n'
        f'\n'
        f'  waitMapper(function(mapper,renderer){{\n'
        f'    fSel.addEventListener("change",function(){{\n'
        f'      var f=fSel.value;\n'
        f'      if(!FIELD_DATA[f]&&f!==ORIGINAL_FIELD)return;\n'
        f'      try{{\n'
        f'        badge.style.display="inline-block";\n'
        f'        badge.innerHTML="&#8230;";\n'
        f'        badge.style.background="#555";\n'
        f'\n'
        f'        var polydata=mapper.getInputData();\n'
        f'        var arr=polydata.getPointData().getArrayByName(ORIGINAL_FIELD);\n'
        f'\n'
        f'        if(f===ORIGINAL_FIELD){{\n'
        f'          // Decode original field data (embedded for round-trip)\n'
        f'          if(FIELD_DATA[f])arr.setData(decodeField(FIELD_DATA[f]),1);\n'
        f'        }}else{{\n'
        f'          arr.setData(decodeField(FIELD_DATA[f]),1);\n'
        f'        }}\n'
        f'        arr.modified();\n'
        f'        polydata.modified();\n'
        f'\n'
        f'        var range=FIELD_RANGES[f];\n'
        f'        if(range)mapper.setScalarRange(range[0],range[1]);\n'
        f'\n'
        f'        // Try to update scalar bar title\n'
        f'        try{{\n'
        f'          var a2d=renderer.getActors2D?renderer.getActors2D():[];\n'
        f'          for(var k=0;k<a2d.length;k++){{if(a2d[k].setTitle)a2d[k].setTitle(f);}}\n'
        f'        }}catch(e2){{}}\n'
        f'\n'
        f'        window.renderWindow.render();\n'
        f'\n'
        f'        badge.innerHTML="&#10003; "+f;\n'
        f'        badge.style.background="rgba(0,140,0,0.85)";\n'
        f'        setTimeout(function(){{badge.style.display="none";}},2000);\n'
        f'\n'
        f'        // Persist selection for PDF export (fire-and-forget; fails silently standalone)\n'
        f'        try{{\n'
        f'          parent.postMessage({{type:"4dpaper-field-update",fig_id:FIG_ID,data:{{field:f}}}},"*");\n'
        f'        }}catch(e3){{}}\n'
        f'\n'
        f'      }}catch(err){{\n'
        f'        badge.innerHTML="&#10007; error";\n'
        f'        badge.style.background="rgba(180,0,0,0.85)";\n'
        f'        badge.style.display="inline-block";\n'
        f'        console.error("[4dpaper] field switch error:",err);\n'
        f'      }}\n'
        f'    }});\n'
        f'  }});\n'
        f'}})();\n'
        f'</script>'
    )


def _time_sync_snippet(
    fig_id: str,
    time_labels: list[str],
    time_data_b64: list[str],
    global_range: list[float],
    initial_idx: int,
    original_field: str,
) -> str:
    """
    Return an HTML+JS snippet for client-side timestep scrubbing.

    Embeds all timestep scalar arrays as base64 Float32Arrays. A timeline
    slider at the bottom centre lets the user scrub through time; on each
    step the active vtk.js array is updated in-place (same setData() approach
    as _field_sync_snippet) and the scene re-renders.

    Uses a global colormap range (computed across all steps) so the colour
    scale stays stable while scrubbing.

    Persists the selected step index via parent.postMessage →
    4dpaper-field-update → /field/<fig_id> (same relay as field switching).

    Returns "" when there is only one timestep (nothing to scrub).
    """
    n = len(time_data_b64)
    if n <= 1:
        return ""

    fig_id_js = json.dumps(fig_id).replace("</", "<\\/")
    fig_id_safe = fig_id.replace("</", "<\\/").replace('"', '')
    original_field_js = json.dumps(original_field).replace("</", "<\\/")
    time_labels_js = json.dumps(time_labels).replace("</", "<\\/")
    time_data_js = json.dumps(time_data_b64).replace("</", "<\\/")
    global_range_js = json.dumps(global_range)
    initial_label = time_labels[initial_idx] if initial_idx < len(time_labels) else str(initial_idx)

    return (
        # ── Timeline slider UI — centred at bottom ────────────────────────
        f'<div id="time-ctrl-{fig_id_safe}"\n'
        f'  style="position:fixed;bottom:8px;left:50%;transform:translateX(-50%);\n'
        f'  z-index:9999;background:rgba(30,30,30,0.88);padding:6px 14px 8px;\n'
        f'  border-radius:6px;font-family:monospace;font-size:11px;color:#eee;\n'
        f'  box-shadow:0 4px 12px rgba(0,0,0,0.5);min-width:280px;max-width:420px;\n'
        f'  display:flex;flex-direction:column;gap:4px;">\n'
        f'  <div style="display:flex;justify-content:space-between;align-items:center;">\n'
        f'    <span style="color:#aaa;">&#128336;&nbsp;t&nbsp;=&nbsp;'
        f'<span id="time-val-{fig_id_safe}">{initial_label}</span></span>\n'
        f'    <span style="color:#666;font-size:10px;">'
        f'step&nbsp;<span id="time-idx-{fig_id_safe}">{initial_idx}</span>'
        f'&nbsp;/&nbsp;{n - 1}</span>\n'
        f'  </div>\n'
        f'  <input type="range" id="time-slider-{fig_id_safe}"\n'
        f'    min="0" max="{n - 1}" value="{initial_idx}"\n'
        f'    style="width:100%;cursor:pointer;margin:0;accent-color:#4a9eff;">\n'
        f'</div>\n'
        # ── JS ────────────────────────────────────────────────────────────
        f'<script>\n'
        f'(function(){{\n'
        f'  var FIG_ID={fig_id_js};\n'
        f'  var TIME_DATA={time_data_js};\n'
        f'  var TIME_LABELS={time_labels_js};\n'
        f'  var GLOBAL_RANGE={global_range_js};\n'
        f'  var ORIGINAL_FIELD={original_field_js};\n'
        f'  var slider=document.getElementById("time-slider-{fig_id_safe}");\n'
        f'  var valSpan=document.getElementById("time-val-{fig_id_safe}");\n'
        f'  var idxSpan=document.getElementById("time-idx-{fig_id_safe}");\n'
        f'  var updateTimer=null;\n'
        f'\n'
        f'  function decodeField(b64){{\n'
        f'    var bin=atob(b64);\n'
        f'    var bytes=new Uint8Array(bin.length);\n'
        f'    for(var i=0;i<bin.length;i++)bytes[i]=bin.charCodeAt(i);\n'
        f'    return new Float32Array(bytes.buffer);\n'
        f'  }}\n'
        f'\n'
        f'  function waitMapper(cb){{\n'
        f'    function check(){{\n'
        f'      var rw=window.renderWindow;\n'
        f'      if(rw&&rw.getRenderers){{\n'
        f'        var renderers=rw.getRenderers();\n'
        f'        for(var i=0;i<renderers.length;i++){{\n'
        f'          var r=renderers[i];\n'
        f'          if(!r||!r.getActors)continue;\n'
        f'          var actors=r.getActors();\n'
        f'          for(var j=0;j<actors.length;j++){{\n'
        f'            var actor=actors[j];\n'
        f'            if(!actor||!actor.getMapper)continue;\n'
        f'            var mapper=actor.getMapper();\n'
        f'            if(!mapper||!mapper.getInputData)continue;\n'
        f'            var pd=mapper.getInputData();\n'
        f'            if(pd&&pd.getPointData&&pd.getPointData().getArrayByName(ORIGINAL_FIELD)){{\n'
        f'              cb(mapper);return;\n'
        f'            }}\n'
        f'          }}\n'
        f'        }}\n'
        f'      }}\n'
        f'      setTimeout(check,200);\n'
        f'    }}\n'
        f'    check();\n'
        f'  }}\n'
        f'\n'
        f'  waitMapper(function(mapper){{\n'
        f'    function applyStep(idx){{\n'
        f'      var b64=TIME_DATA[idx];\n'
        f'      if(!b64)return;\n'
        f'      try{{\n'
        f'        var polydata=mapper.getInputData();\n'
        f'        var arr=polydata.getPointData().getArrayByName(ORIGINAL_FIELD);\n'
        f'        arr.setData(decodeField(b64),1);\n'
        f'        arr.modified();\n'
        f'        polydata.modified();\n'
        f'        mapper.setScalarRange(GLOBAL_RANGE[0],GLOBAL_RANGE[1]);\n'
        f'        window.renderWindow.render();\n'
        f'        try{{\n'
        f'          parent.postMessage({{type:"4dpaper-field-update",fig_id:FIG_ID,'
        f'data:{{time:String(idx)}}}},"*");\n'
        f'        }}catch(e2){{}}\n'
        f'      }}catch(err){{\n'
        f'        console.error("[4dpaper] time step error:",err);\n'
        f'      }}\n'
        f'    }}\n'
        f'\n'
        f'    slider.addEventListener("input",function(){{\n'
        f'      var idx=parseInt(slider.value);\n'
        f'      // Instant label update\n'
        f'      if(TIME_LABELS[idx]!==undefined)valSpan.textContent=TIME_LABELS[idx];\n'
        f'      idxSpan.textContent=idx;\n'
        f'      // Debounced mesh update (100 ms) — avoids redraw on every pixel\n'
        f'      clearTimeout(updateTimer);\n'
        f'      updateTimer=setTimeout(function(){{applyStep(idx);}},100);\n'
        f'    }});\n'
        f'  }});\n'
        f'}})();\n'
        f'</script>'
    )


# ── Figure generation (Task 3) ────────────────────────────────────────────────

def generate_png_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
) -> None:
    """
    Generate a static PNG figure using PyVista.

    If a saved camera JSON exists at state/camera_<fig_id>.json, the saved
    camera position is applied; otherwise falls back to isometric view.
    Used as a fallback for PDF export.
    """
    import pyvista as pv
    from scripts.data_loader import SimulationData

    sim = SimulationData(str(src_path)).load()

    if sim.n_steps == 0:
        raise RuntimeError(
            f"[4dpaper] Simulation at {src_path} has no time steps."
        )

    n = sim.n_steps
    if time_spec == "first":
        idx = 0
    elif time_spec == "last":
        idx = max(0, n - 1)
    else:
        try:
            idx = max(0, min(int(time_spec), n - 1))
        except ValueError:
            idx = n // 2

    mesh = sim.get_mesh(idx)
    if mesh is None:
        raise RuntimeError(f"[4dpaper] Could not load mesh at step {idx} from {src_path}")

    surface = mesh.extract_surface(algorithm='dataset_surface')

    pl = pv.Plotter(off_screen=True, window_size=(1920, 1080))
    pl.background_color = "#1a1a2e"

    if field and (field in surface.point_data or field in surface.cell_data):
        pl.add_mesh(
            surface,
            scalars=field,
            cmap="coolwarm",
            smooth_shading=True,
            scalar_bar_args={"title": field},
        )
    else:
        pl.add_mesh(surface, color="#aaaaaa", opacity=0.9)
        print(
            f"[4dpaper] Warning: field '{field}' not found — rendering geometry only.",
            file=sys.stderr,
        )

    # Apply saved camera if available, else fall back to isometric view.
    camera_path = (_project_root / "state" / f"camera_{fig_id}.json" if fig_id else None)
    apply_camera_state(pl, fig_id or "unnamed", camera_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(output_path))
    pl.close()
    print(f"[4dpaper] Generated (PNG): {output_path}")


def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
    available_fields: list[str] | None = None,
) -> None:
    """
    Generate a self-contained vtk.js HTML figure using PyVista.

    Uses PyVista's Plotter.export_html() which produces a standalone
    file powered by panel + trame — no server required to view.
    """
    import pyvista as pv
    from scripts.data_loader import SimulationData

    sim = SimulationData(str(src_path)).load()

    if sim.n_steps == 0:
        raise RuntimeError(
            f"[4dpaper] Simulation at {src_path} has no time steps. "
            "Ensure the case has been solved and time directories exist."
        )

    # Resolve time step index
    n = sim.n_steps
    if time_spec == "first":
        idx = 0
    elif time_spec == "last":
        idx = max(0, n - 1)
    else:  # "mid" or numeric string
        try:
            idx = max(0, min(int(time_spec), n - 1))
        except ValueError:
            idx = n // 2

    mesh = sim.get_mesh(idx)
    if mesh is None:
        raise RuntimeError(f"[4dpaper] Could not load mesh at step {idx} from {src_path}")

    surface = mesh.extract_surface(algorithm='dataset_surface')

    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = "#1a1a2e"

    if field and (field in surface.point_data or field in surface.cell_data):
        pl.add_mesh(
            surface,
            scalars=field,
            cmap="coolwarm",
            smooth_shading=True,
            scalar_bar_args={"title": field},
        )
    else:
        pl.add_mesh(surface, color="#aaaaaa", opacity=0.9)
        print(
            f"[4dpaper] Warning: field '{field}' not found in mesh — rendering geometry only.",
            file=sys.stderr,
        )

    # Apply camera — same logic as generate_png_figure so HTML and PDF start from
    # the same viewpoint.
    camera_path = (_project_root / "state" / f"camera_{fig_id}.json" if fig_id else None)
    apply_camera_state(pl, fig_id or "unnamed", camera_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.export_html(str(output_path))
    pl.close()

    # ── Prepare field data blobs for live switching ───────────────────────────
    # For each switchable field (other than the one already rendered), extract
    # the scalar array as Float32, cell→point interpolated to match what
    # trame serialises for the active field, then base64-encode for injection.
    import base64 as _b64
    fields_to_embed = list(available_fields) if available_fields else [field]
    field_data_b64: dict[str, str] = {}
    field_ranges: dict[str, list[float]] = {}

    # Convert cell data → point data once (matches vtk.js rendering path)
    surf_pts = None

    def _get_arr(f: str):
        nonlocal surf_pts
        if f in surface.point_data:
            return surface.point_data[f]
        if f in surface.cell_data:
            if surf_pts is None:
                surf_pts = surface.cell_data_to_point_data()
            if f in surf_pts.point_data:
                return surf_pts.point_data[f]
        return None

    for f in fields_to_embed:
        arr_np = _get_arr(f)
        if arr_np is None:
            print(f"[4dpaper] Warning: field '{f}' not found — skipping from switcher.", file=sys.stderr)
            continue
        arr_f32 = arr_np.astype("float32").ravel()
        field_data_b64[f] = _b64.b64encode(arr_f32.tobytes()).decode("ascii")
        field_ranges[f] = [float(arr_f32.min()), float(arr_f32.max())]

    # ── Prepare time step data blobs (one per step, active field only) ────────
    # Each entry is a base64 Float32Array of the scalar values at that step.
    # Empty string is used as a placeholder when a step's data is unavailable.
    time_data_b64: list[str] = []
    time_labels: list[str] = []
    time_global_min = float("inf")
    time_global_max = float("-inf")

    if sim.n_steps > 1 and field:
        print(
            f"[4dpaper] {fig_id or 'fig'}: embedding {sim.n_steps} timesteps for timeline …",
            file=sys.stderr,
        )
        for t_idx in range(sim.n_steps):
            t_mesh = sim.get_mesh(t_idx)
            if t_mesh is None:
                time_data_b64.append("")
                time_labels.append(str(t_idx))
                continue
            t_surface = t_mesh.extract_surface(algorithm="dataset_surface")
            # Get scalar array — same cell→point conversion logic as _get_arr
            arr_np = None
            if field in t_surface.point_data:
                arr_np = t_surface.point_data[field]
            elif field in t_surface.cell_data:
                t_pts = t_surface.cell_data_to_point_data()
                if field in t_pts.point_data:
                    arr_np = t_pts.point_data[field]
            if arr_np is not None:
                arr_f32 = arr_np.astype("float32").ravel()
                time_data_b64.append(_b64.b64encode(arr_f32.tobytes()).decode("ascii"))
                time_global_min = min(time_global_min, float(arr_f32.min()))
                time_global_max = max(time_global_max, float(arr_f32.max()))
            else:
                time_data_b64.append("")
            # Human-readable time label (physical time value from the reader)
            if t_idx < len(sim.time_steps):
                time_labels.append(f"{sim.time_steps[t_idx]:.4g}")
            else:
                time_labels.append(str(t_idx))

    time_global_range = (
        [time_global_min, time_global_max]
        if time_global_min != float("inf")
        else [0.0, 1.0]
    )

    # Patch viewport units so the widget has a fixed height when embedded inline.
    # PyVista's trame output uses 100vw/100vh which fills the whole page.
    html = output_path.read_text()
    html = html.replace("100vw", "900px").replace("100vh", "600px")

    if fig_id:
        if "</body>" not in html:
            print(
                f"[4dpaper] Warning: no </body> in {output_path.name} "
                "— camera sync badge not injected.",
                file=sys.stderr,
            )
        else:
            inj_html = (
                _camera_sync_snippet(fig_id)
                + "\n"
                + _field_sync_snippet(fig_id, fields_to_embed, field, field_data_b64, field_ranges)
                + "\n"
                + _time_sync_snippet(fig_id, time_labels, time_data_b64, time_global_range, idx, field)
                + "\n</body>"
            )
            html = html.replace("</body>", inj_html, 1)
    output_path.write_text(html)

    print(f"[4dpaper] Generated: {output_path}", file=sys.stderr)


def generate_panel_html(panel: dict, figures_dir: Path) -> None:
    """
    Generate a composite HTML file embedding multiple vtk.js figures in a CSS grid.

    Layout convention: "COLSxROWS" e.g. "2x2" = 2 columns 2 rows.
    Output: figures_dir/<panel-id>.html — a single self-contained file.

    Camera sync: a bidirectional re-relay script forwards camera/field messages
    from child srcdoc iframes up to top (Quarto relay), and acks back down to
    all children so each sub-figure's camera badge works correctly.
    """
    layout = panel["layout"]
    try:
        ncols_s, nrows_s = layout.split("x")
        ncols, nrows = int(ncols_s), int(nrows_s)
    except (ValueError, AttributeError):
        raise ValueError(
            f"[4dpaper] 4d-panel layout must be 'COLSxROWS' (e.g. '2x2', '3x1'), got: '{layout}'"
        )

    height = panel.get("height", "800px")

    # Generate each sub-figure HTML (reuses caching inside generate_html_figure)
    for sub in panel["subfigures"]:
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        out = figures_dir / f"{sub['id']}.html"
        generate_html_figure(src, sub["field"], sub["time"], out, fig_id=sub["id"])

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

    grid_style = (
        f'display:grid;grid-template-columns:repeat({ncols},1fr);'
        f'grid-template-rows:repeat({nrows},1fr);gap:4px;'
        f'width:100%;height:{height};background:#111;'
    )

    cells = []
    for sub in panel["subfigures"]:
        content = (figures_dir / f"{sub['id']}.html").read_text()
        escaped = content.replace("&", "&amp;").replace('"', "&quot;")
        cells.append(
            f'<iframe srcdoc="{escaped}" '
            f'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
        )

    composite = (
        f'<!DOCTYPE html><html><body style="margin:0;padding:0;">'
        f'{re_relay}'
        f'<div style="{grid_style}">'
        + "".join(cells)
        + f'</div></body></html>'
    )

    out_path = figures_dir / f"{panel['id']}.html"
    out_path.write_text(composite)
    print(f"[4dpaper] Generated panel (HTML): {out_path}", file=sys.stderr)


# ── Video figure generation ───────────────────────────────────────────────────

def _build_video_html_fragment(b64: str, fig_id: str, escaped_preview: str) -> str:
    """
    Build the HTML fragment for a video figure with an embedded camera-setup modal.

    The modal contains a vtk.js interactive preview (deferred srcdoc) so the user
    can rotate to the desired camera angle. Rotating fires the camera sync snippet
    inside the preview, which postMessages to the parent page relay (injected by
    fourd_video in shortcodes.lua) and saves state/camera_<fig_id>.json.

    Parameters
    ----------
    b64: base64-encoded MP4 bytes (for the data URI)
    fig_id: figure identifier string
    escaped_preview: the preview HTML with & → &amp; and " → &quot; (safe for
                     embedding in a double-quoted HTML attribute)
    """
    onclick = (
        f"var f=document.getElementById('cam-iframe-{fig_id}');"
        "if(!f.getAttribute('data-loaded'))"
        "{f.srcdoc=f.getAttribute('data-srcdoc');f.setAttribute('data-loaded','1');}"
        f"document.getElementById('cam-modal-{fig_id}').style.display='flex';"
    )
    close_onclick = f"document.getElementById('cam-modal-{fig_id}').style.display='none'"
    return (
        f'<div style="position:relative;display:inline-block;width:100%;max-width:900px;">\n'
        f'  <video src="data:video/mp4;base64,{b64}"\n'
        f'    controls loop autoplay muted playsinline\n'
        f'    style="width:100%;height:600px;border-radius:4px;display:block;">\n'
        f'  </video>\n'
        f'  <button id="cam-open-{fig_id}"\n'
        f'    onclick="{onclick}"\n'
        f'    style="position:absolute;top:8px;right:8px;background:rgba(20,20,50,0.85);'
        f'color:#fff;border:1px solid #555;border-radius:4px;padding:5px 10px;'
        f'cursor:pointer;font-size:12px;font-family:monospace;">\n'
        f'    &#128247; Camera View\n'
        f'  </button>\n'
        f'</div>\n'
        f'<!-- Camera view modal -->\n'
        f'<div id="cam-modal-{fig_id}"\n'
        f'  style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.82);'
        f'z-index:10000;justify-content:center;align-items:center;">\n'
        f'  <div style="background:#1a1a2e;border-radius:8px;padding:16px;'
        f'width:min(940px,96vw);box-shadow:0 8px 32px rgba(0,0,0,0.6);">\n'
        f'    <div style="display:flex;justify-content:space-between;'
        f'align-items:center;margin-bottom:8px;">\n'
        f'      <span style="color:#ccc;font-size:12px;font-family:monospace;">\n'
        f'        &#128247; Rotate to set camera &mdash; syncs automatically on mouse release\n'
        f'        &mdash; then click <b>Rebuild HTML</b>\n'
        f'      </span>\n'
        f'      <button onclick="{close_onclick}"\n'
        f'        style="background:none;border:none;color:#999;font-size:20px;'
        f'cursor:pointer;padding:0 4px;">\n'
        f'        &#10005;\n'
        f'      </button>\n'
        f'    </div>\n'
        f'    <iframe id="cam-iframe-{fig_id}"\n'
        f'      data-srcdoc="{escaped_preview}"\n'
        f'      srcdoc=""\n'
        f'      width="900" height="600"\n'
        f'      frameborder="0"\n'
        f'      style="border:none;border-radius:4px;display:block;">\n'
        f'    </iframe>\n'
        f'    <p style="color:#666;font-size:10px;margin:4px 0 0;'
        f'text-align:right;font-family:monospace;">\n'
        f'      fig id: {fig_id}\n'
        f'    </p>\n'
        f'  </div>\n'
        f'</div>'
    )


def generate_video_figure(
    src_path: Path,
    field: str,
    fps: int,
    time_spec: str,
    mp4_path: Path,
    frame_path: Path,
    video_html_path: Path,
    fig_id: str,
    preview_html_path: Path | None = None,
) -> None:
    """
    Generate an MP4 animation + PDF frame PNG + HTML fragment for a 4d-video shortcode.

    Uses a two-pass approach: Pass 1 computes the global scalar range across all
    timesteps; Pass 2 renders each frame with a fixed color scale. The MP4 is
    base64-encoded into a minimal HTML fragment so Lua can embed it directly.

    If preview_html_path is None, it defaults to <video_html_path.parent>/<fig_id>-preview.html.
    An interactive vtk.js preview (one timestep) is always generated alongside the video
    and embedded as a deferred srcdoc in the camera-setup modal button.
    """
    import base64
    import pyvista as pv
    import imageio
    from scripts.data_loader import SimulationData

    sim = SimulationData(str(src_path)).load()
    n_steps = sim.n_steps
    if n_steps == 0:
        raise RuntimeError(f"[4dpaper] Simulation at {src_path} has no time steps.")

    # Pass 1 — compute global scalar range across all timesteps
    print(f"[4dpaper] {fig_id}: computing global range over {n_steps} frames …", file=sys.stderr)
    global_min = float("inf")
    global_max = float("-inf")
    for idx in range(n_steps):
        mesh = sim.get_mesh(idx)
        if mesh is None:
            continue
        if field in mesh.point_data:
            arr = mesh.point_data[field]
        elif field in mesh.cell_data:
            arr = mesh.cell_data[field]
        else:
            continue
        global_min = min(global_min, float(arr.min()))
        global_max = max(global_max, float(arr.max()))
    if global_min == float("inf"):
        print(
            f"[4dpaper] Warning: field '{field}' not found — rendering geometry only.",
            file=sys.stderr,
        )
        global_min, global_max = 0.0, 1.0

    # Read camera JSON once (avoid re-reading disk on every frame)
    camera_path = _project_root / "state" / f"camera_{fig_id}.json"
    camera_data: dict | None = None
    if camera_path.exists():
        try:
            camera_data = json.loads(camera_path.read_text())
        except Exception:
            pass

    # Pass 2 — render each frame and write MP4
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[4dpaper] {fig_id}: rendering {n_steps} frames at {fps} fps …", file=sys.stderr)
    writer = imageio.get_writer(
        str(mp4_path),
        fps=fps,
        codec="libx264",
        pixelformat="yuv420p",
        quality=7,
        format="mp4",
        macro_block_size=1,
    )
    try:
        for idx in range(n_steps):
            mesh = sim.get_mesh(idx)
            if mesh is None:
                continue
            surface = mesh.extract_surface(algorithm="dataset_surface")
            pl = pv.Plotter(off_screen=True, window_size=(900, 600))
            pl.background_color = "#1a1a2e"
            if field and (field in surface.point_data or field in surface.cell_data):
                pl.add_mesh(
                    surface,
                    scalars=field,
                    cmap="coolwarm",
                    clim=[global_min, global_max],
                    smooth_shading=True,
                    scalar_bar_args={"title": field},
                )
            else:
                pl.add_mesh(surface, color="#aaaaaa", opacity=0.9)
            _apply_camera_from_dict(pl, fig_id, camera_data)
            frame = pl.screenshot(return_img=True)
            pl.close()
            writer.append_data(frame)
            if (idx + 1) % 10 == 0 or idx == n_steps - 1:
                print(
                    f"[4dpaper] {fig_id}: frame {idx + 1}/{n_steps}",
                    file=sys.stderr,
                )
    finally:
        writer.close()
    print(f"[4dpaper] Generated (MP4): {mp4_path}", file=sys.stderr)

    # Generate PDF frame (representative timestep, full resolution)
    if time_spec == "first":
        frame_idx = 0
    elif time_spec == "last":
        frame_idx = max(0, n_steps - 1)
    else:
        try:
            frame_idx = max(0, min(int(time_spec), n_steps - 1))
        except ValueError:
            frame_idx = n_steps // 2

    mesh = sim.get_mesh(frame_idx)
    if mesh is not None:
        surface = mesh.extract_surface(algorithm="dataset_surface")
        pl = pv.Plotter(off_screen=True, window_size=(1920, 1080))
        pl.background_color = "#1a1a2e"
        if field and (field in surface.point_data or field in surface.cell_data):
            pl.add_mesh(
                surface,
                scalars=field,
                cmap="coolwarm",
                clim=[global_min, global_max],
                smooth_shading=True,
                scalar_bar_args={"title": field},
            )
        else:
            pl.add_mesh(surface, color="#aaaaaa", opacity=0.9)
        _apply_camera_from_dict(pl, fig_id, camera_data)
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        pl.screenshot(str(frame_path))
        pl.close()
        print(f"[4dpaper] Generated (frame PNG): {frame_path}", file=sys.stderr)

    # Generate interactive vtk.js preview for the camera-setup modal
    if preview_html_path is None:
        preview_html_path = video_html_path.parent / f"{fig_id}-preview.html"
    try:
        generate_html_figure(
            src_path, field, time_spec,
            preview_html_path,
            fig_id=fig_id,
            available_fields=[field] if field else [],
        )
        preview_raw = preview_html_path.read_text()
        escaped_preview = preview_raw.replace("&", "&amp;").replace('"', "&quot;")
    except Exception as exc:
        print(
            f"[4dpaper] Warning: could not generate preview for {fig_id}: {exc}. "
            "Camera modal will be empty.",
            file=sys.stderr,
        )
        escaped_preview = ""

    # Build self-contained HTML fragment with base64-encoded MP4 data URI
    b64 = base64.b64encode(mp4_path.read_bytes()).decode("ascii")
    video_html = _build_video_html_fragment(b64, fig_id, escaped_preview)
    video_html_path.parent.mkdir(parents=True, exist_ok=True)
    video_html_path.write_text(video_html)
    print(f"[4dpaper] Generated (video HTML): {video_html_path}", file=sys.stderr)


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    if os.environ.get("QUARTO_NO_EXECUTE"):
        print("[4dpaper] --no-execute mode: skipping figure generation.", file=sys.stderr)
        return

    qmd_path = os.environ.get("QUARTO_DOCUMENT_PATH", "")
    # QUARTO_OUTPUT_FORMAT is not reliably set for project-level pre-render hooks.
    # We always generate both .html and .png so both HTML and PDF output work.
    output_format = os.environ.get("QUARTO_OUTPUT_FORMAT", "html")  # kept for logging only

    # QUARTO_DOCUMENT_PATH is not always set for project-level pre-render hooks.
    # Fall back to scanning all .qmd files in QUARTO_PROJECT_DIR (or project root).
    if qmd_path and Path(qmd_path).exists():
        qmd_files = [Path(qmd_path)]
    else:
        project_dir = Path(os.environ.get("QUARTO_PROJECT_DIR", str(_project_root)))
        qmd_files = sorted(project_dir.glob("*.qmd"))
        if not qmd_files:
            print("[4dpaper] No .qmd files found — skipping.", file=sys.stderr)
            return
        print(f"[4dpaper] Scanning {len(qmd_files)} QMD file(s) in {project_dir}", file=sys.stderr)

    figures = []
    videos = []
    for qmd in qmd_files:
        text = qmd.read_text()
        figures.extend(parse_shortcodes(text))
        videos.extend(parse_video_shortcodes(text))

    if not figures and not videos:
        print("[4dpaper] No 4d-image or 4d-video shortcodes found.", file=sys.stderr)
        return

    figures_dir = _project_root / "state" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    for fig in figures:
        fig_id = fig["id"]
        src = Path(fig["src"]) if Path(fig["src"]).is_absolute() else _project_root / fig["src"]
        field = fig["field"]
        time_spec = fig.get("time", "mid")

        # Parse available_fields from shortcode attribute "fields" (comma-separated).
        # Falls back to [field] (single field, no switcher) if not specified.
        fields_attr = fig.get("fields", "").strip()
        if fields_attr:
            available_fields = [f.strip() for f in fields_attr.split(",") if f.strip()]
            # Ensure the active field is always present
            if field and field not in available_fields:
                available_fields.insert(0, field)
        else:
            available_fields = [field] if field else []

        field_state_path = _project_root / "state" / f"field_{fig_id}.json"
        if field_state_path.exists():
            try:
                state_data = json.loads(field_state_path.read_text())
                if "field" in state_data:
                    field = state_data["field"]
                if "time" in state_data:
                    time_spec = state_data["time"]
            except Exception:
                pass

        # Always generate both .html (for web) and .png (for PDF).
        # QUARTO_OUTPUT_FORMAT is not reliably set for project pre-render hooks,
        # so we keep both formats up to date on every render pass.
        out_html = figures_dir / f"{fig_id}.html"
        # Also invalidate HTML cache if this script itself changed (e.g. new camera snippet).
        script_newer = (
            out_html.exists()
            and _here.stat().st_mtime > out_html.stat().st_mtime
        )
        if not script_newer and is_cache_valid(out_html, src, field_path=field_state_path):
            print(f"[4dpaper] {fig_id}.html is up to date — skipping.", file=sys.stderr)
        else:
            print(f"[4dpaper] Generating {fig_id}.html …", file=sys.stderr)
            try:
                generate_html_figure(
                    src, field, time_spec, out_html,
                    fig_id=fig_id, available_fields=available_fields,
                )
            except Exception as exc:
                print(f"[4dpaper] ERROR generating {fig_id}.html: {exc}", file=sys.stderr)
                sys.exit(1)

        out_png = figures_dir / f"{fig_id}.png"
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"
        # Always report camera status so the user can verify what's used in PDF.
        if camera_path.exists():
            try:
                cam = json.loads(camera_path.read_text())
                print(
                    f"[4dpaper] Camera for {fig_id}: position={cam.get('position')}  "
                    f"(from state/camera_{fig_id}.json — rotate the 3D figure in the "
                    f"HTML preview to update)"
                )
            except Exception:
                print(f"[4dpaper] Camera for {fig_id}: file exists but is invalid — will use isometric view")
        else:
            print(
                f"[4dpaper] Camera for {fig_id}: NOT SET — isometric view will be used. "
                f"Rotate the figure in the HTML preview to save a camera position."
            )
        # Always regenerate PNG when a camera file exists...
        png_fresh = is_cache_valid(out_png, src, camera_path=camera_path, field_path=field_state_path)
        if png_fresh:
            print(f"[4dpaper] {fig_id}.png is up to date — skipping.")
        else:
            print(f"[4dpaper] Generating {fig_id}.png …")
            try:
                generate_png_figure(src, field, time_spec, out_png, fig_id=fig_id)
            except Exception as exc:
                print(f"[4dpaper] ERROR generating {fig_id}.png: {exc}")
                sys.exit(1)

    # ── Video shortcode processing ─────────────────────────────────────────────
    for vid in videos:
        fig_id = vid["id"]
        src = Path(vid["src"]) if Path(vid["src"]).is_absolute() else _project_root / vid["src"]
        field = vid["field"]
        time_spec = vid.get("time", "mid")
        fps = int(vid.get("fps", "10"))

        mp4_path = figures_dir / f"{fig_id}-video.mp4"
        frame_path = figures_dir / f"{fig_id}-frame.png"
        video_html_path = figures_dir / f"{fig_id}-video.html"
        preview_html_path = figures_dir / f"{fig_id}-preview.html"
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"

        mp4_valid = is_cache_valid(mp4_path, src, camera_path=camera_path)
        frame_valid = is_cache_valid(frame_path, src, camera_path=camera_path)
        # Also invalidate video HTML when this script changes (contains injected content)
        script_newer_vid = (
            video_html_path.exists()
            and _here.stat().st_mtime > video_html_path.stat().st_mtime
        )
        html_valid = (
            not script_newer_vid
            and is_cache_valid(video_html_path, src, camera_path=camera_path)
        )

        if mp4_valid and frame_valid and html_valid:
            print(f"[4dpaper] {fig_id} video outputs are up to date — skipping.", file=sys.stderr)
            continue

        print(f"[4dpaper] Generating video for {fig_id} …", file=sys.stderr)
        try:
            generate_video_figure(
                src, field, fps, time_spec,
                mp4_path, frame_path, video_html_path,
                fig_id=fig_id,
                preview_html_path=preview_html_path,
            )
        except Exception as exc:
            print(f"[4dpaper] ERROR generating video {fig_id}: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
