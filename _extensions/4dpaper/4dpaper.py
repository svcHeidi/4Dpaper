#!/usr/bin/env python3
"""
4DPaper pre-render hook — run by Quarto before rendering.

Scans the .qmd for {{< 4d-image >}} shortcodes and generates
figure files in state/figures/ (HTML for web, PNG for PDF, and optional
experimental U3D/PRC assets for interactive PDF via media9).

Quarto calls this script before rendering. It reads QUARTO_DOCUMENT_PATH
and QUARTO_OUTPUT_FORMAT from the environment.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
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


def parse_vtk_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-vtk key="value" ... >}} shortcodes from QMD text.

    Returns a list of dicts with at minimum 'id' and 'spec' keys.
    Shortcodes missing 'id' or 'spec' are silently skipped.
    """
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)

    pattern = r'\{\{<\s*4d-vtk\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "spec" not in kwargs:
            continue
        kwargs.setdefault("caption", "")
        results.append(kwargs)
    return results


# ── Cache helpers ─────────────────────────────────────────────────────────────

def is_cache_valid(
    fig_path: Path,
    src_path: Path,
    camera_path: Path | None = None,
    extra_deps: list[Path] | None = None,
) -> bool:
    """
    Return True if fig_path exists, is newer than src_path, camera_path
    (if given and present), and all extra_deps that exist.

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
    for dep in extra_deps or []:
        if dep.exists() and fig_mtime <= dep.stat().st_mtime:
            return False
    return True


def _truthy_env(name: str, default: bool = False) -> bool:
    """Return a boolean parsed from environment variable ``name``."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_time_index(time_spec: str, n_steps: int) -> int:
    """Resolve time selector string ('first'/'last'/index/'mid') into index."""
    if n_steps <= 0:
        raise ValueError("n_steps must be positive")
    if time_spec == "first":
        return 0
    if time_spec == "last":
        return max(0, n_steps - 1)
    try:
        return max(0, min(int(time_spec), n_steps - 1))
    except ValueError:
        return n_steps // 2


def _run_converter_template(template: str, input_path: Path, output_path: Path) -> tuple[bool, str]:
    """Run a converter command template with {input}/{output} placeholders."""
    try:
        cmd = template.format(input=str(input_path), output=str(output_path))
    except (KeyError, ValueError, IndexError) as exc:
        return False, f"invalid converter template: {exc}"
    argv = shlex.split(cmd)
    if not argv:
        return False, "empty command"
    exe = argv[0]
    if shutil.which(exe) is None:
        return False, f"missing executable: {exe}"
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
        return False, err
    if not output_path.exists() or output_path.stat().st_size == 0:
        return False, "converter succeeded but output file is missing or empty"
    return True, ""


def _candidate_converter_templates(kind: str) -> list[str]:
    """Return ordered converter command templates for U3D/PRC generation."""
    templates: list[str] = []
    if kind == "u3d":
        custom = os.environ.get("FOURDPAPER_U3D_CONVERTER_CMD", "").strip()
        if custom:
            templates.append(custom)
        # Best-effort built-ins when no custom converter is configured.
        templates.extend([
            "assimp export {input} {output}",
            "meshlabserver -i {input} -o {output}",
        ])
    elif kind == "prc":
        custom = os.environ.get("FOURDPAPER_PRC_CONVERTER_CMD", "").strip()
        if custom:
            templates.append(custom)
    return templates


def generate_pdf3d_asset(
    src_path: Path,
    field: str,
    time_spec: str,
    output_dir: Path,
    fig_id: str,
) -> Path | None:
    """Generate experimental U3D/PRC asset for interactive PDF embedding.

    This uses external conversion tools; configure one or both:
      - FOURDPAPER_U3D_CONVERTER_CMD
      - FOURDPAPER_PRC_CONVERTER_CMD

    Command templates must include ``{input}`` and ``{output}`` placeholders.
    Example:
      FOURDPAPER_U3D_CONVERTER_CMD="assimp export {input} {output}"
    """
    from scripts.data_loader import SimulationData

    sim = SimulationData(str(src_path)).load()
    if sim.n_steps == 0:
        raise RuntimeError(f"[4dpaper] Simulation at {src_path} has no time steps.")

    idx = _resolve_time_index(time_spec, sim.n_steps)
    mesh = sim.get_mesh(idx)
    if mesh is None:
        raise RuntimeError(f"[4dpaper] Could not load mesh at step {idx} from {src_path}")
    surface = mesh.extract_surface()

    preferred = os.environ.get("FOURDPAPER_PDF3D_FORMAT", "auto").strip().lower()
    order = ["u3d", "prc"] if preferred in ("", "auto") else [preferred]
    order = [k for k in order if k in {"u3d", "prc"}]
    if not order:
        print(
            f"[4dpaper] Unsupported FOURDPAPER_PDF3D_FORMAT='{preferred}' (expected auto/u3d/prc).",
            file=sys.stderr,
        )
        return None

    intermediate = os.environ.get("FOURDPAPER_PDF3D_INTERMEDIATE", "obj").strip().lower()
    if intermediate not in {"obj", "ply"}:
        print(
            f"[4dpaper] Unsupported FOURDPAPER_PDF3D_INTERMEDIATE='{intermediate}' "
            "(expected obj/ply).",
            file=sys.stderr,
        )
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="4dpaper-pdf3d-") as tmpdir:
        tmp_dir = Path(tmpdir)
        if intermediate == "ply":
            mesh_input = tmp_dir / f"{fig_id}.ply"
            _mesh_to_pdf3d_ply(surface, field, mesh_input, compress=False)
        else:
            mesh_input = tmp_dir / f"{fig_id}.obj"
            surface.save(str(mesh_input))

        for kind in order:
            out_path = output_dir / f"{fig_id}.{kind}"
            for template in _candidate_converter_templates(kind):
                ok, err = _run_converter_template(template, mesh_input, out_path)
                if ok:
                    print(f"[4dpaper] Generated PDF 3D asset: {out_path}", file=sys.stderr)
                    return out_path
                print(
                    f"[4dpaper] {kind.upper()} converter failed ({template}): {err}",
                    file=sys.stderr,
                )

    print(
        "[4dpaper] Could not generate U3D/PRC asset. "
        "Set FOURDPAPER_U3D_CONVERTER_CMD or FOURDPAPER_PRC_CONVERTER_CMD.",
        file=sys.stderr,
    )
    return None


def _mesh_to_pdf3d_ply(
    mesh,
    field: str,
    output_path: Path,
    *,
    compress: bool = True,
) -> Path:
    """
    Convert a mesh to a compact, field-colored PLY asset for PDF 3D experiments.

    The output is a surface-only PolyData with RGB vertex colors derived from
    the selected scalar field using a fixed publication colormap.
    """
    import numpy as np
    import pyvista as pv
    from matplotlib import colormaps
    from scripts.data_loader import SimulationData

    surface = mesh.extract_surface()
    if field and field in surface.point_data:
        scalars = np.asarray(surface.point_data[field], dtype=float)
    elif field and field in surface.cell_data:
        surface = surface.cell_data_to_point_data()
        scalars = np.asarray(surface.point_data[field], dtype=float)
    else:
        raise RuntimeError(
            f"[4dpaper] Field '{field}' not found on extracted surface for PDF3D PLY export."
        )

    if scalars.size == 0:
        raise RuntimeError(f"[4dpaper] Field '{field}' is empty on extracted surface.")

    finite = scalars[np.isfinite(scalars)]
    if finite.size == 0:
        raise RuntimeError(f"[4dpaper] Field '{field}' has no finite values on extracted surface.")

    vmin = float(finite.min())
    vmax = float(finite.max())
    span = vmax - vmin
    if span <= 1e-12:
        norm = np.zeros_like(scalars, dtype=float)
    else:
        norm = np.clip((scalars - vmin) / span, 0.0, 1.0)
    norm = np.nan_to_num(norm, nan=0.0, posinf=1.0, neginf=0.0)

    colors = (colormaps["coolwarm"](norm)[:, :3] * 255.0).astype(np.uint8)
    ply_mesh = pv.PolyData(surface.points, surface.faces)
    # PLY color export goes through the texture argument in PyVista's writer.
    ply_mesh.point_data["RGB"] = colors

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ply_mesh.save(str(output_path), texture="RGB")

    if compress:
        gz_path = SimulationData.compress_ply(str(output_path))
        print(f"[4dpaper] Generated compressed PDF3D PLY asset: {gz_path}", file=sys.stderr)
        return gz_path

    print(f"[4dpaper] Generated PDF3D PLY asset: {output_path}", file=sys.stderr)
    return output_path


def export_pdf3d_ply_asset(
    src_path: Path,
    field: str,
    time_spec: str,
    output_dir: Path,
    fig_id: str,
    *,
    compress: bool = True,
) -> Path:
    """
    Export a compact, field-colored PLY surface asset for future PDF 3D pipelines.

    This is a test implementation that prepares a surface-only artifact with
    RGB vertex colors derived from the selected scalar field. It does not yet
    replace the OBJ -> U3D/PRC converter flow, but provides a dedicated export
    artifact for evaluating PLY-based PDF3D conversion.
    """
    from scripts.data_loader import SimulationData

    sim = SimulationData(str(src_path)).load()
    if sim.n_steps == 0:
        raise RuntimeError(f"[4dpaper] Simulation at {src_path} has no time steps.")

    idx = _resolve_time_index(time_spec, sim.n_steps)
    mesh = sim.get_mesh(idx)
    if mesh is None:
        raise RuntimeError(f"[4dpaper] Could not load mesh at step {idx} from {src_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    ply_path = output_dir / f"{fig_id}.pdf3d.ply"
    return _mesh_to_pdf3d_ply(mesh, field, ply_path, compress=compress)


def _project_relative_posix(path: Path) -> str:
    """Return ``path`` as a project-relative POSIX string when possible."""
    try:
        return path.resolve().relative_to(_project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _write_pdf3d_tex_snippet(
    tex_path: Path,
    poster_path: Path,
    asset_path: Path,
    width: str = "0.90\\linewidth",
    height: str = "0.56\\linewidth",
) -> None:
    """Write LaTeX snippet that uses media9 when available, else poster fallback."""
    poster_rel = _latex_path_escape(_project_relative_posix(poster_path))
    asset_rel = _latex_path_escape(_project_relative_posix(asset_path))
    # Use \ifdefined\includemedia rather than checking for media9.sty because
    # shortcodes are rendered in document body (cannot safely call \usepackage there).
    snippet = (
        f"% Auto-generated by 4DPaper for interactive PDF (experimental)\n"
        f"\\ifdefined\\includemedia\n"
        f"\\includemedia[\n"
        f"  width={width},\n"
        f"  height={height},\n"
        f"  activate=pageopen,\n"
        f"  deactivate=pageclose,\n"
        f"  3Dtoolbar,\n"
        f"  3Dmenu,\n"
        f"  addresource={{{asset_rel}}}\n"
        f"]{{\\includegraphics[width={width}]{{{poster_rel}}}}}{{{asset_rel}}}\n"
        f"\\else\n"
        f"\\includegraphics[width={width}]{{{poster_rel}}}\n"
        f"\\fi\n"
    )
    tex_path.write_text(snippet)


def _latex_escape(text: str) -> str:
    """Escape text for safe use inside a LaTeX caption."""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def _latex_path_escape(path: str) -> str:
    """Escape filesystem path for safe use inside LaTeX file arguments."""
    return (
        path.replace("\\", "/")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("#", r"\#")
        .replace("_", r"\_")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace(" ", r"\ ")
    )


def generate_pdf3d_tex_figure(
    fig_id: str,
    caption: str,
    png_path: Path,
    asset_path: Path | None,
    output_tex_path: Path,
) -> bool:
    """Write a LaTeX figure include for experimental interactive PDF.

    If ``asset_path`` is provided, write a media9-enabled snippet.
    Otherwise write a PNG-only fallback snippet, so PDF build remains valid.
    """
    output_tex_path.parent.mkdir(parents=True, exist_ok=True)
    png_rel = _latex_path_escape(_project_relative_posix(png_path))
    cap = _latex_escape(caption) if caption else ""
    label = _latex_escape(fig_id)

    if asset_path is not None and asset_path.exists():
        _write_pdf3d_tex_snippet(output_tex_path, poster_path=png_path, asset_path=asset_path)
        base = output_tex_path.read_text()
        figure_tex = [
            r"\begin{figure}[htbp]",
            r"\centering",
            base.strip(),
        ]
        if cap:
            figure_tex.append(rf"\caption{{{cap}}}")
        figure_tex.append(rf"\label{{fig:{label}}}")
        figure_tex.append(r"\end{figure}")
        output_tex_path.write_text("\n".join(figure_tex) + "\n")
        return True

    fallback = [
        r"\begin{figure}[htbp]",
        r"\centering",
        rf"\includegraphics[width=0.90\linewidth]{{{png_rel}}}",
    ]
    if cap:
        fallback.append(rf"\caption{{{cap}}}")
    fallback.append(rf"\label{{fig:{label}}}")
    fallback.append(r"\end{figure}")
    output_tex_path.write_text("\n".join(fallback) + "\n")
    return True


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


def _camera_path(fig_id: str | None) -> Path | None:
    """Return the saved camera JSON path for a figure id, if provided."""
    if not fig_id:
        return None
    return _project_root / "state" / f"camera_{fig_id}.json"


def _apply_saved_camera(pl, fig_id: str | None, *, context: str = "figure") -> None:
    """
    Apply a saved camera JSON if present, else use isometric view.

    The camera JSON comes from the vtk.js renderer that has actors, which
    operates in the same world coordinate space as PyVista — so we can
    apply position / focal_point / view_up directly.
    """
    camera_path = _camera_path(fig_id)
    if camera_path is not None and camera_path.exists():
        try:
            cam = json.loads(camera_path.read_text())
            pl.camera.position = cam["position"]
            pl.camera.focal_point = cam["focal_point"]
            pl.camera.up = cam["view_up"]
            print(f"[4dpaper] {context} {fig_id}: using saved camera", file=sys.stderr)
            return
        except (json.JSONDecodeError, KeyError) as exc:
            print(
                f"[4dpaper] Warning: could not apply saved camera for {fig_id} ({exc})"
                " — using isometric view.",
                file=sys.stderr,
            )
    pl.isometric_view()


def _postprocess_exported_html(output_path: Path, fig_id: str | None = None) -> None:
    """Normalize exported HTML sizing and inject camera sync when applicable."""
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


def load_render_spec(spec_path: Path) -> dict:
    """
    Load and validate a VTK render specification JSON file.

    Relative mesh paths are resolved relative to the spec file location.
    """
    if not spec_path.exists():
        raise RuntimeError(f"[4dpaper] Render spec not found: {spec_path}")

    try:
        raw = json.loads(spec_path.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"[4dpaper] Invalid render spec JSON at {spec_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise RuntimeError(f"[4dpaper] Render spec must be a JSON object: {spec_path}")

    mesh_value = str(raw.get("mesh", "")).strip()
    if not mesh_value:
        raise RuntimeError(f"[4dpaper] Render spec missing required 'mesh': {spec_path}")

    field_raw = raw.get("field")
    if not isinstance(field_raw, dict):
        raise RuntimeError(f"[4dpaper] Render spec missing required 'field' object: {spec_path}")

    field_name = str(field_raw.get("name", "")).strip()
    if not field_name:
        raise RuntimeError(f"[4dpaper] Render spec missing required 'field.name': {spec_path}")

    association = str(field_raw.get("association", "point")).strip().lower() or "point"
    if association not in {"point", "cell"}:
        raise RuntimeError(
            f"[4dpaper] Render spec field.association must be 'point' or 'cell': {spec_path}"
        )

    field_range = field_raw.get("range")
    if field_range is not None:
        if not isinstance(field_range, list) or len(field_range) != 2:
            raise RuntimeError(
                f"[4dpaper] Render spec field.range must be a two-item list: {spec_path}"
            )
        try:
            field_range = [float(field_range[0]), float(field_range[1])]
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"[4dpaper] Render spec field.range must contain numbers: {spec_path}"
            ) from exc

    filter_raw = raw.get("filter", {})
    if filter_raw is None:
        filter_raw = {}
    if not isinstance(filter_raw, dict):
        raise RuntimeError(f"[4dpaper] Render spec 'filter' must be an object: {spec_path}")
    filter_kind = str(filter_raw.get("kind", "none")).strip().lower() or "none"
    if filter_kind not in {"none", "surface"}:
        raise RuntimeError(
            f"[4dpaper] Render spec filter.kind must be 'none' or 'surface': {spec_path}"
        )

    display_raw = raw.get("display", {})
    if display_raw is None:
        display_raw = {}
    if not isinstance(display_raw, dict):
        raise RuntimeError(f"[4dpaper] Render spec 'display' must be an object: {spec_path}")

    source_raw = raw.get("source", {})
    if source_raw is None:
        source_raw = {}
    if not isinstance(source_raw, dict):
        raise RuntimeError(f"[4dpaper] Render spec 'source' must be an object: {spec_path}")

    source_mode = str(source_raw.get("mode", "file")).strip().lower() or "file"
    if source_mode not in {"file", "simulation"}:
        raise RuntimeError(
            f"[4dpaper] Render spec source.mode must be 'file' or 'simulation': {spec_path}"
        )

    mesh_path = Path(mesh_value)
    if not mesh_path.is_absolute():
        mesh_path = (spec_path.parent / mesh_path).resolve()

    time_spec = str(raw.get("time", "mid")).strip() or "mid"
    part_name = str(raw.get("part", "internalMesh")).strip() or "internalMesh"

    return {
        "version": int(raw.get("version", 1)),
        "spec_path": spec_path,
        "mesh": mesh_value,
        "mesh_path": mesh_path,
        "source": {"mode": source_mode, "time": time_spec, "part": part_name},
        "time": time_spec,
        "part": part_name,
        "field": {
            "name": field_name,
            "association": association,
            "range": field_range,
            "colormap": str(field_raw.get("colormap", "coolwarm")).strip() or "coolwarm",
        },
        "filter": {"kind": filter_kind},
        "display": {
            "background": str(display_raw.get("background", "#1a1a2e")).strip() or "#1a1a2e",
            "show_scalar_bar": bool(display_raw.get("show_scalar_bar", True)),
        },
    }


def prepare_render_mesh(mesh, filter_kind: str):
    """Apply a geometry filter policy before rendering."""
    if filter_kind == "none":
        return mesh
    if filter_kind == "surface":
        return mesh.extract_surface()
    raise ValueError(f"Unsupported filter kind: {filter_kind}")


def _load_render_spec_mesh(spec: dict):
    """
    Load the dataset referenced by a render spec.

    The primary path is direct VTK-family loading via ``pyvista.read``. For
    time-dependent simulation sources such as OpenFOAM, fall back to the
    existing ``SimulationData`` loader so render specs can temporarily point to
    the same source files used by ``4d-image``.
    """
    import pyvista as pv

    mesh_path = spec["mesh_path"]
    if mesh_path.suffix.lower() in {".foam", ".pvd", ".case"}:
        from scripts.data_loader import SimulationData

        sim = SimulationData(str(mesh_path)).load()
        if sim.n_steps == 0:
            raise RuntimeError(
                f"[4dpaper] Simulation at {mesh_path} has no time steps. "
                "Ensure the case has been solved and time directories exist."
            )
        idx = _resolve_time_index(spec["time"], sim.n_steps)
        mesh = sim.get_mesh(idx, part=spec["part"])
        if mesh is None:
            raise RuntimeError(
                f"[4dpaper] Could not load mesh at step {idx} from {mesh_path}"
            )
        return mesh

    return pv.read(str(mesh_path))


def _compute_field_range(mesh, field_name: str, association: str) -> list[float] | None:
    """Return [min, max] for the requested field on the requested association."""
    import numpy as np

    data = mesh.point_data if association == "point" else mesh.cell_data
    if field_name not in data:
        return None
    arr = np.asarray(data[field_name])
    if arr.size == 0:
        return None
    return [float(np.nanmin(arr)), float(np.nanmax(arr))]


def _add_render_spec_mesh(pl, mesh, spec: dict) -> None:
    """Add a render-spec-configured mesh to a PyVista plotter."""
    field = spec["field"]["name"]
    association = spec["field"]["association"]
    field_range = spec["field"]["range"]
    cmap = spec["field"]["colormap"]
    show_scalar_bar = spec["display"]["show_scalar_bar"]

    data = mesh.point_data if association == "point" else mesh.cell_data
    if field and field in data:
        add_kwargs = {
            "scalars": field,
            "preference": association,
            "cmap": cmap,
            "smooth_shading": True,
            "show_scalar_bar": show_scalar_bar,
        }
        effective_range = field_range or _compute_field_range(mesh, field, association)
        if effective_range is not None:
            add_kwargs["clim"] = effective_range
        if show_scalar_bar:
            add_kwargs["scalar_bar_args"] = {"title": field}
        pl.add_mesh(mesh, **add_kwargs)
    else:
        pl.add_mesh(mesh, color="#aaaaaa", opacity=0.9)
        print(
            f"[4dpaper] Warning: field '{field}' not found for {association} data"
            " — rendering geometry only.",
            file=sys.stderr,
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

    _apply_saved_camera(pl, fig_id, context="PNG figure")
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

    _apply_saved_camera(pl, fig_id, context="HTML figure")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.export_html(str(output_path))
    pl.close()
    _postprocess_exported_html(output_path, fig_id=fig_id)

    print(f"[4dpaper] Generated: {output_path}", file=sys.stderr)


def generate_png_from_render_spec(
    spec_path: Path,
    output_path: Path,
    fig_id: str | None = None,
) -> None:
    """Generate a static PNG figure from a VTK render specification."""
    import pyvista as pv

    spec = load_render_spec(spec_path)
    mesh = pv.read(str(spec["mesh_path"]))
    render_mesh = prepare_render_mesh(mesh, spec["filter"]["kind"])

    pl = pv.Plotter(off_screen=True, window_size=(1920, 1080))
    pl.background_color = spec["display"]["background"]
    _add_render_spec_mesh(pl, render_mesh, spec)
    _apply_saved_camera(pl, fig_id, context="VTK PNG figure")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(output_path))
    pl.close()
    print(f"[4dpaper] Generated (VTK PNG): {output_path}", file=sys.stderr)


def generate_html_from_render_spec(
    spec_path: Path,
    output_path: Path,
    fig_id: str | None = None,
) -> None:
    """Generate a self-contained vtk.js HTML figure from a VTK render specification."""
    import pyvista as pv

    spec = load_render_spec(spec_path)
    mesh = pv.read(str(spec["mesh_path"]))
    render_mesh = prepare_render_mesh(mesh, spec["filter"]["kind"])

    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = spec["display"]["background"]
    _add_render_spec_mesh(pl, render_mesh, spec)
    _apply_saved_camera(pl, fig_id, context="VTK HTML figure")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.export_html(str(output_path))
    pl.close()
    _postprocess_exported_html(output_path, fig_id=fig_id)
    print(f"[4dpaper] Generated (VTK HTML): {output_path}", file=sys.stderr)


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
    vtk_figs = []
    for qmd in qmd_files:
        text = qmd.read_text()
        figures.extend(parse_shortcodes(text))
        vtk_figs.extend(parse_vtk_shortcodes(text))

    if not figures and not vtk_figs:
        print("[4dpaper] No 4d-image or 4d-vtk shortcodes found.", file=sys.stderr)
        return

    pdf3d_enabled = _truthy_env("FOURDPAPER_PDF3D_EXPERIMENTAL", default=False)
    pdf3d_target_id = os.environ.get("FOURDPAPER_PDF3D_TARGET_ID", "fig-vm").strip() or "fig-vm"

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

        if pdf3d_enabled and fig_id == pdf3d_target_id:
            print(
                f"[4dpaper] Experimental PDF 3D mode enabled for '{fig_id}'. "
                "Attempting U3D/PRC asset generation.",
                file=sys.stderr,
            )
            pdf3d_asset = generate_pdf3d_asset(
                src_path=src,
                field=field,
                time_spec=time_spec,
                output_dir=figures_dir,
                fig_id=fig_id,
            )
            tex_out = figures_dir / f"{fig_id}.pdf3d.tex"
            tex_ok = generate_pdf3d_tex_figure(
                fig_id=fig_id,
                caption=fig.get("caption", ""),
                png_path=out_png,
                asset_path=pdf3d_asset,
                output_tex_path=tex_out,
            )
            if tex_ok:
                print(
                    f"[4dpaper] Wrote experimental media9 TeX include: {tex_out}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[4dpaper] media9 TeX include fallback failed for {fig_id}; keeping PNG-only PDF.",
                    file=sys.stderr,
                )

    for vtk_fig in vtk_figs:
        fig_id = vtk_fig["id"]
        spec_path = (
            Path(vtk_fig["spec"])
            if Path(vtk_fig["spec"]).is_absolute()
            else _project_root / vtk_fig["spec"]
        )
        try:
            render_spec = load_render_spec(spec_path)
        except Exception as exc:
            print(f"[4dpaper] ERROR loading render spec for {fig_id}: {exc}", file=sys.stderr)
            sys.exit(1)

        mesh_path = render_spec["mesh_path"]
        out_html = figures_dir / f"{fig_id}.html"
        script_newer = (
            out_html.exists()
            and _here.stat().st_mtime > out_html.stat().st_mtime
        )
        camera_path = _camera_path(fig_id)
        if not script_newer and is_cache_valid(
            out_html,
            spec_path,
            camera_path=camera_path,
            extra_deps=[mesh_path],
        ):
            print(f"[4dpaper] {fig_id}.html is up to date — skipping.", file=sys.stderr)
        else:
            print(f"[4dpaper] Generating {fig_id}.html from render spec …", file=sys.stderr)
            try:
                generate_html_from_render_spec(spec_path, out_html, fig_id=fig_id)
            except Exception as exc:
                print(f"[4dpaper] ERROR generating {fig_id}.html: {exc}", file=sys.stderr)
                sys.exit(1)

        out_png = figures_dir / f"{fig_id}.png"
        png_fresh = (
            not camera_path.exists()
            and is_cache_valid(out_png, spec_path, extra_deps=[mesh_path])
        )
        if png_fresh:
            print(f"[4dpaper] {fig_id}.png is up to date — skipping.")
        else:
            print(f"[4dpaper] Generating {fig_id}.png from render spec …")
            try:
                generate_png_from_render_spec(spec_path, out_png, fig_id=fig_id)
            except Exception as exc:
                print(f"[4dpaper] ERROR generating {fig_id}.png: {exc}")
                sys.exit(1)

if __name__ == "__main__":
    main()
