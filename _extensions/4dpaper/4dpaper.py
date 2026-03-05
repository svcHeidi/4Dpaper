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
        results.append(kwargs)
    return results


# ── Cache helpers ─────────────────────────────────────────────────────────────

def is_cache_valid(
    fig_path: Path,
    src_path: Path,
    camera_path: Path | None = None,
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
    return True


# ── Camera orientation transfer ───────────────────────────────────────────────


def _apply_camera_orientation(pl, surface, cam_data: dict) -> None:
    """
    Apply *orientation only* from a vtk.js camera to a PyVista plotter.

    vtk.js exports camera in normalised scene coordinates, while PyVista
    uses real-world mesh coordinates.  Rather than transferring absolute
    positions (which would place the camera far from the mesh), we:

    1. Extract the **view direction** (position → focal_point) and **up vector**
       from the vtk.js camera.
    2. Compute an appropriate camera distance from the mesh bounding sphere.
    3. Set the PyVista camera: focal point = mesh center, position = center +
       direction × distance, up = vtk.js up vector.
    """
    import numpy as np

    pos = np.array(cam_data["position"], dtype=float)
    fpt = np.array(cam_data["focal_point"], dtype=float)
    up = np.array(cam_data["view_up"], dtype=float)

    # View direction: from focal point towards the camera position
    direction = pos - fpt
    length = np.linalg.norm(direction)
    if length < 1e-12:
        # Degenerate — fall back to isometric
        pl.isometric_view()
        return
    direction = direction / length

    # Mesh bounding sphere radius
    bounds = np.array(surface.bounds).reshape(3, 2)
    center = bounds.mean(axis=1)
    extents = bounds[:, 1] - bounds[:, 0]
    radius = np.linalg.norm(extents) / 2.0

    # Place camera at 3× bounding-sphere radius (comfortable framing)
    distance = radius * 3.0

    pl.camera.focal_point = center.tolist()
    pl.camera.position = (center + direction * distance).tolist()
    pl.camera.up = up.tolist()


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
        f'          view_up:cam.getViewUp()\n'
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

    surface = mesh.extract_surface()

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
    # The camera JSON comes from the vtk.js renderer that has actors, which
    # operates in the same world coordinate space as PyVista — so we can
    # apply position / focal_point / view_up directly.
    camera_path = (
        _project_root / "state" / f"camera_{fig_id}.json"
        if fig_id else None
    )
    if camera_path is not None and camera_path.exists():
        try:
            cam = json.loads(camera_path.read_text())
            pl.camera.position = cam["position"]
            pl.camera.focal_point = cam["focal_point"]
            pl.camera.up = cam["view_up"]
            print(f"[4dpaper] Applied saved camera for {fig_id}")
        except (json.JSONDecodeError, KeyError) as exc:
            print(
                f"[4dpaper] Warning: could not apply saved camera for {fig_id} ({exc})"
                " — using isometric view.",
            )
            pl.isometric_view()
    else:
        pl.isometric_view()
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

    surface = mesh.extract_surface()

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
    # the same viewpoint.  If a saved camera JSON exists, use it; otherwise fall
    # back to isometric view.  This guarantees the initial HTML figure and the
    # exported PDF always show the same default angle.
    camera_path = (
        _project_root / "state" / f"camera_{fig_id}.json"
        if fig_id else None
    )
    if camera_path is not None and camera_path.exists():
        try:
            cam = json.loads(camera_path.read_text())
            pl.camera.position = cam["position"]
            pl.camera.focal_point = cam["focal_point"]
            pl.camera.up = cam["view_up"]
            print(f"[4dpaper] HTML figure {fig_id}: using saved camera", file=sys.stderr)
        except (json.JSONDecodeError, KeyError) as exc:
            print(
                f"[4dpaper] Warning: could not apply saved camera for {fig_id} ({exc})"
                " — using isometric view.",
                file=sys.stderr,
            )
            pl.isometric_view()
    else:
        pl.isometric_view()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.export_html(str(output_path))
    pl.close()

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
            html = html.replace("</body>", _camera_sync_snippet(fig_id) + "\n</body>", 1)
    output_path.write_text(html)

    print(f"[4dpaper] Generated: {output_path}", file=sys.stderr)


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
    for qmd in qmd_files:
        figures.extend(parse_shortcodes(qmd.read_text()))

    if not figures:
        print("[4dpaper] No 4d-image shortcodes found.", file=sys.stderr)
        return

    figures_dir = _project_root / "state" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    for fig in figures:
        fig_id = fig["id"]
        src = Path(fig["src"]) if Path(fig["src"]).is_absolute() else _project_root / fig["src"]
        field = fig["field"]
        time_spec = fig.get("time", "mid")

        # Always generate both .html (for web) and .png (for PDF).
        # QUARTO_OUTPUT_FORMAT is not reliably set for project pre-render hooks,
        # so we keep both formats up to date on every render pass.
        out_html = figures_dir / f"{fig_id}.html"
        # Also invalidate HTML cache if this script itself changed (e.g. new camera snippet).
        script_newer = (
            out_html.exists()
            and _here.stat().st_mtime > out_html.stat().st_mtime
        )
        if not script_newer and is_cache_valid(out_html, src):
            print(f"[4dpaper] {fig_id}.html is up to date — skipping.", file=sys.stderr)
        else:
            print(f"[4dpaper] Generating {fig_id}.html …", file=sys.stderr)
            try:
                generate_html_figure(src, field, time_spec, out_html, fig_id=fig_id)
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
        # Always regenerate PNG when a camera file exists — the user may
        # have rotated the interactive figure since the last export and we
        # want the PDF to reflect the latest viewpoint.  When there is no
        # camera file, fall back to the standard source-based cache check.
        png_fresh = (
            not camera_path.exists()
            and is_cache_valid(out_png, src)
        ) if camera_path else is_cache_valid(out_png, src)
        if png_fresh:
            print(f"[4dpaper] {fig_id}.png is up to date — skipping.")
        else:
            print(f"[4dpaper] Generating {fig_id}.png …")
            try:
                generate_png_figure(src, field, time_spec, out_png, fig_id=fig_id)
            except Exception as exc:
                print(f"[4dpaper] ERROR generating {fig_id}.png: {exc}")
                sys.exit(1)


if __name__ == "__main__":
    main()
