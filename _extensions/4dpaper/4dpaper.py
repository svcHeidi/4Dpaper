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


# ── Camera sync snippet ───────────────────────────────────────────────────────

def _camera_sync_snippet(fig_id: str, server_url: str = "http://localhost:5006") -> str:
    """
    Return an HTML+JS snippet that:
    - Shows a '📷 Default view' badge (position:fixed, top-right of iframe)
    - After each rotation end, POSTs {position, focal_point, view_up} to the server
    - Updates the badge to '📷 Camera synced' on success

    vtk.js exposes window.renderWindow after OfflineLocalView.load() is called.
    The interactor's onEndInteractionEvent fires after each drag ends.
    The fetch is debounced 500ms so rapid drags only send one request.
    """
    fig_id_js = json.dumps(fig_id).replace("</", "<\\/")
    # Embed the camera endpoint prefix (server_url + "/camera/") as a literal
    # string so that tests can assert its presence directly in the snippet source.
    camera_prefix_js = json.dumps(server_url.rstrip("/") + "/camera/").replace("</", "<\\/")
    # Escape </  in the raw fig_id used inside the script body (e.g. getElementById arg)
    # so that a fig_id containing </script> cannot break out of the <script> block.
    fig_id_safe = fig_id.replace("</", "<\\/")
    return (
        f'<div id="camera-badge-{fig_id}" style="position:fixed;top:8px;right:8px;'
        f'background:rgba(80,80,80,0.75);color:#fff;padding:4px 8px;'
        f'border-radius:4px;font-size:11px;font-family:monospace;'
        f'z-index:9999;pointer-events:none;">&#128247; Default view</div>\n'
        f'<script>\n'
        f'(function(){{\n'
        f'  var FIG_ID={fig_id_js}, CAM_PREFIX={camera_prefix_js};\n'
        f'  var badge=document.getElementById("camera-badge-{fig_id_safe}");\n'
        f'  var timer=null;\n'
        f'  function waitRW(cb){{\n'
        f'    if(window.renderWindow){{cb(window.renderWindow);}}\n'
        f'    else{{var iv=setInterval(function(){{if(window.renderWindow){{clearInterval(iv);cb(window.renderWindow);}}}},100);}}\n'
        f'  }}\n'
        f'  waitRW(function(rw){{\n'
        f'    rw.getInteractor().onEndInteractionEvent(function(){{\n'
        f'      clearTimeout(timer);\n'
        f'      timer=setTimeout(function(){{\n'
        f'        var cam=rw.getRenderers().getFirst().getActiveCamera();\n'
        f'        fetch(CAM_PREFIX+FIG_ID,{{\n'
        f'          method:"POST",\n'
        f'          headers:{{"Content-Type":"application/json"}},\n'
        f'          body:JSON.stringify({{\n'
        f'            position:cam.getPosition(),\n'
        f'            focal_point:cam.getFocalPoint(),\n'
        f'            view_up:cam.getViewUp()\n'
        f'          }})\n'
        f'        }}).then(function(r){{\n'
        f'          if(r.ok){{badge.innerHTML="&#128247; Camera synced";'
        f'badge.style.background="rgba(0,160,0,0.75)";}}\n'
        f'        }}).catch(function(){{\n'
        f'          badge.innerHTML="&#128247; Sync error";\n'
        f'          badge.style.background="rgba(180,0,0,0.75)";\n'
        f'        }});\n'
        f'      }},500);\n'
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

    # Apply saved camera if available, else fall back to isometric view
    camera_path = (
        _project_root / "state" / f"camera_{fig_id}.json"
        if fig_id else None
    )
    if camera_path is not None and camera_path.exists():
        try:
            cam = json.loads(camera_path.read_text())
            pl.camera.position = cam["position"]
            pl.camera.focal_point = cam["focal_point"]
            pl.camera.view_up = cam["view_up"]
            print(f"[4dpaper] Applied saved camera for {fig_id}", file=sys.stderr)
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
    pl.screenshot(str(output_path))
    pl.close()
    print(f"[4dpaper] Generated (PNG): {output_path}", file=sys.stderr)


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
        if is_cache_valid(out_html, src):
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
        if is_cache_valid(out_png, src, camera_path=camera_path):
            print(f"[4dpaper] {fig_id}.png is up to date — skipping.", file=sys.stderr)
        else:
            print(f"[4dpaper] Generating {fig_id}.png …", file=sys.stderr)
            try:
                generate_png_figure(src, field, time_spec, out_png, fig_id=fig_id)
            except Exception as exc:
                print(f"[4dpaper] ERROR generating {fig_id}.png: {exc}", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
