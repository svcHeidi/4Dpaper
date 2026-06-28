#!/usr/bin/env python3
"""Render 4DPaper shortcode assets before Quarto runs."""
from __future__ import annotations

import base64 as _b64
import json
import os
import re
import sys
from pathlib import Path

# Apply nest_asyncio early to allow trame's async server in non-Jupyter contexts
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

_here = Path(__file__).resolve()
_project_root = Path(
    os.environ.get("PROJECT_ROOT")
    or os.environ.get("QUARTO_PROJECT_DIR")
    or str(_here.parent.parent.parent)
)


def _resolve_app_root() -> Path | None:
    """Locate the 4Dpapers app root that provides `dashboard` and `scripts`."""
    candidates: list[Path] = []
    for raw in (
        os.environ.get("FOURD_APP_ROOT"),
        str(_here.parent.parent.parent),
        "/app",
    ):
        if not raw:
            continue
        candidate = Path(raw)
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if (candidate / "dashboard").is_dir() and (candidate / "scripts").is_dir():
            return candidate
    return None


_app_root = _resolve_app_root()
_venv_python = _project_root / ".venv" / "bin" / "python"
_under_pytest = "pytest" in sys.modules or any("pytest" in a for a in sys.argv)
if (
    _venv_python.exists()
    and not _under_pytest
    and Path(sys.executable).resolve() != _venv_python.resolve()
):
    # Safety: assert the resolved venv python lives inside the project root before
    # handing control to it.  Prevents a crafted PROJECT_ROOT env var from
    # redirecting execv to an arbitrary binary.
    _venv_resolved = _venv_python.resolve()
    _root_resolved = _project_root.resolve()
    if _venv_resolved.is_relative_to(_root_resolved):
        os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)
    else:
        print(
            f"WARNING: venv python '{_venv_resolved}' is outside project root "
            f"'{_root_resolved}' — skipping execv re-launch for safety.",
            file=sys.stderr,
        )


for _path in (_app_root, _project_root):
    if _path is not None and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import importlib.util as _ilu
_sr_spec = _ilu.spec_from_file_location("shortcut_resolver", _here.parent / "shortcut_resolver.py")
_sr_mod = _ilu.module_from_spec(_sr_spec)
_sr_spec.loader.exec_module(_sr_mod)
ShortcutResolver = _sr_mod.ShortcutResolver

from dashboard.document_signing import sign_html_file_if_configured

_shortcut_resolver = ShortcutResolver(
    config_path=_project_root / "_shortcuts.yml",
    project_root=_project_root
)
_shortcuts_yml_path = _project_root / "_shortcuts.yml"


def _maybe_sign_output_html(output_path: Path) -> None:
    """Apply a trailing signature block when HTML signing is configured."""
    if sign_html_file_if_configured(output_path):
        print(f"Signed HTML: {output_path}", file=sys.stderr)


def resolve_src_path(src_str: str) -> Path:
    """Resolve a source path with optional `@shortcut` syntax."""
    try:
        return _shortcut_resolver.resolve(src_str)
    except ValueError as exc:
        print(f"Warning: {exc}", file=sys.stderr)
        path = Path(src_str)
        return path if path.is_absolute() else _project_root / path


def _rdp_simplify_xy(
    xs: list,
    ys: list,
    epsilon_fraction: float = 0.001,
) -> tuple[list, list]:
    """Simplify an `(x, y)` polyline with iterative RDP."""
    import numpy as np

    try:
        x = np.asarray(xs, dtype=float)
        y = np.asarray(ys, dtype=float)
    except (TypeError, ValueError):
        return xs, ys

    n = len(x)
    if n != len(y) or n < 3:
        return xs, ys

    x_rng = x.max() - x.min()
    y_rng = y.max() - y.min()
    xn = (x - x.min()) / x_rng if x_rng > 0 else np.zeros(n)
    yn = (y - y.min()) / y_rng if y_rng > 0 else np.zeros(n)

    pts = np.column_stack([xn, yn])
    eps = float(epsilon_fraction)

    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[-1] = True

    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        p1 = pts[start]
        p2 = pts[end]
        d = p2 - p1
        norm = np.linalg.norm(d)
        seg = pts[start + 1:end]
        if norm == 0:
            dists = np.linalg.norm(seg - p1, axis=1)
        else:
            dists = np.abs(np.cross(d, seg - p1)) / norm
        max_local = int(np.argmax(dists))
        if dists[max_local] > eps:
            mid = start + 1 + max_local
            keep[mid] = True
            stack.append((start, mid))
            stack.append((mid, end))

    idx = np.where(keep)[0]
    return x[idx].tolist(), y[idx].tolist()


_DECIMATE_TARGET_FACES = 150_000


def _surface_cell_count(surface) -> int:
    """Return a stable cell count across PyVista versions."""
    return int(getattr(surface, "n_cells", 0))


def _decimate_quadric(surface, target_faces: int):
    import math
    import vtk
    bounds = surface.bounds
    dx = bounds[1] - bounds[0]
    dy = bounds[3] - bounds[2]
    dz = bounds[5] - bounds[4]
    max_dim = max(dx, dy, dz)
    
    n = int(math.sqrt(target_faces / 3.0))
    n = max(10, min(n, 256))
    
    nx = max(10, int(n * (dx / max_dim))) if max_dim > 0 else 10
    ny = max(10, int(n * (dy / max_dim))) if max_dim > 0 else 10
    nz = max(10, int(n * (dz / max_dim))) if max_dim > 0 else 10
    
    cluster = vtk.vtkQuadricClustering()
    cluster.SetInputData(surface)
    cluster.SetUseInputPoints(True)
    cluster.CopyCellDataOn()
    cluster.SetNumberOfXDivisions(nx)
    cluster.SetNumberOfYDivisions(ny)
    cluster.SetNumberOfZDivisions(nz)
    cluster.Update()
    
    import pyvista as pv
    return pv.wrap(cluster.GetOutput())

def _decimate_surface(surface, target_faces: int = _DECIMATE_TARGET_FACES,
                      target_reduction: float | None = None):
    """Decimate a surface when it exceeds the face target."""
    n_faces = _surface_cell_count(surface)
    if target_reduction is not None:
        ratio = float(target_reduction)
        target_faces = int(n_faces * (1.0 - ratio))
    else:
        if n_faces <= target_faces:
            return surface
        ratio = 1.0 - target_faces / n_faces

    ratio = max(0.0, min(ratio, 0.99))
    try:
        return surface.decimate_pro(
            ratio,
            feature_angle=15.0,
            splitting=True,
            boundary_vertex_deletion=False,
            preserve_topology=False,
        )
    except Exception as exc:
        if "all triangles" in str(exc):
            try:
                if "vtkOriginalCellIds" in surface.cell_data:
                    del surface.cell_data["vtkOriginalCellIds"]
                if "vtkOriginalPointIds" in surface.point_data:
                    del surface.point_data["vtkOriginalPointIds"]
                surface = surface.triangulate()
                return surface.decimate_pro(
                    ratio,
                    feature_angle=15.0,
                    splitting=True,
                    boundary_vertex_deletion=False,
                    preserve_topology=False,
                )
            except Exception as e2:
                print(
                    f"WARNING: decimate_pro failed after triangulation ({e2}) — falling back to vtkQuadricClustering.",
                    file=sys.stderr,
                )
                try:
                    return _decimate_quadric(surface, target_faces)
                except Exception as e3:
                    print(f"WARNING: QuadricClustering failed ({e3}) — using original.", file=sys.stderr)
                    return surface
        print(
            f"WARNING: decimate_pro failed ({exc}) — falling back to vtkQuadricClustering.",
            file=sys.stderr,
        )
        try:
            return _decimate_quadric(surface, target_faces)
        except Exception as e3:
            print(f"WARNING: QuadricClustering failed ({e3}) — using original.", file=sys.stderr)
            return surface


def _apply_decimation(surface, decimate_spec: str, label: str = ""):
    """Apply the parsed `decimate` shortcode setting."""
    spec = (decimate_spec or "auto").strip().lower()
    if spec in ("0", "none", "off", "false", "no"):
        return surface

    target_reduction: float | None = None
    if spec != "auto":
        try:
            val = float(spec)
            if val <= 0.0:
                return surface
            target_reduction = min(val, 0.99)
        except ValueError:
            pass

    n_before = _surface_cell_count(surface)
    result = _decimate_surface(surface, target_reduction=target_reduction)
    n_after = _surface_cell_count(result)
    if n_after < n_before and n_before > 0:
        pct = 100.0 * (1.0 - n_after / n_before)
        print(
            f"{label}: decimated {n_before:,} → {n_after:,} faces ({pct:.1f}% reduction)",
            file=sys.stderr,
        )
    return result


def parse_video_shortcodes(text: str) -> list[dict]:
    """Parse `4d-video` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-video\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("fps", "10")
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        kwargs.setdefault("stride", "1")
        results.append(kwargs)
    return results


def parse_shortcodes(text: str) -> list[dict]:
    """Parse `4d-image` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)

    pattern = r'\{\{<\s*4d-image\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        kwargs.setdefault("fields", "")
        kwargs.setdefault("style", "")
        kwargs.setdefault("decimate", "auto")
        kwargs.setdefault("stride", "1")
        results.append(kwargs)
    return results


def parse_panel_shortcodes(text: str) -> list[dict]:
    """Parse `4d-panel` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-panel\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs:
            print("Warning: 4d-panel shortcode missing 'id' — skipping.", file=sys.stderr)
            continue
        subfigures = []
        n = 1
        while f"src{n}" in kwargs:
            subfigures.append({
                "src":    kwargs[f"src{n}"],
                "id":     kwargs.get(f"id{n}", f"panel-sub-{n}"),
                "field":  kwargs.get(f"field{n}", ""),
                "time":   kwargs.get(f"time{n}", "mid"),
                "fields": kwargs.get(f"fields{n}", ""),
            })
            n += 1
        if not subfigures:
            print(f"Warning: 4d-panel '{kwargs['id']}' has no sub-figures — skipping.", file=sys.stderr)
            continue
        results.append({
            "id":          kwargs["id"],
            "layout":      kwargs.get("layout", "1x1"),
            "height":      kwargs.get("height", "800px"),
            "caption":     kwargs.get("caption", ""),
            "camera_mode": kwargs.get("camera", "independent"),
            "subfigures":  subfigures,
        })
    return results


def parse_timeseries_shortcodes(text: str) -> list[dict]:
    """Parse `4d-timeseries` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-timeseries\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs:
            print("Warning: 4d-timeseries shortcode missing 'id' — skipping.", file=sys.stderr)
            continue
        if "src" not in kwargs:
            print("Warning: 4d-timeseries shortcode missing 'src' — skipping.", file=sys.stderr)
            continue
        results.append({
            "id":          kwargs["id"],
            "layout":      None,
            "height":      kwargs.get("height", "400px"),
            "caption":     kwargs.get("caption", ""),
            "camera_mode": "sync",
            "timeseries":  True,
            "src":         kwargs["src"],
            "field":       kwargs.get("field", ""),
            "steps":       kwargs.get("steps", "4"),
            "times":       kwargs.get("times", ""),
            "subfigures":  [],
        })
    return results


def _expand_timeseries_steps(ts: dict, n_steps: int) -> list[int]:
    """Expand `steps` or `times` into step indices."""
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
                    pass
        if result:
            return result
    if n_steps <= 1:
        print(
            f"WARNING: timeseries '{ts['id']}' source has only {n_steps} step(s) "
            "— generating single frame.", file=sys.stderr
        )
        return [0]
    N = max(2, int(ts.get("steps", "4")))
    return [round(i * (n_steps - 1) / (N - 1)) for i in range(N)]


def parse_graph_shortcodes(text: str) -> list[dict]:
    """Parse `4d-graph` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-graph\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("caption", "")
        results.append(kwargs)
    return results


def _check_same_mesh_timeseries(src: Path, step_indices: list[int]) -> bool:
    """Check if all timesteps have identical mesh geometry."""
    try:
        import pyvista as pv
        from scripts.data_loader import SimulationData

        sim = SimulationData(str(src)).load()
        if not step_indices or len(step_indices) < 2:
            return True

        ref_mesh = sim.get_mesh(step_indices[0])
        if ref_mesh is None:
            return False

        ref_n_cells = ref_mesh.n_cells
        ref_n_points = ref_mesh.n_points

        for idx in step_indices[1:]:
            mesh = sim.get_mesh(idx)
            if mesh is None or mesh.n_cells != ref_n_cells or mesh.n_points != ref_n_points:
                return False
        return True
    except Exception as exc:
        print(f"Warning: could not check mesh identity: {exc}", file=sys.stderr)
        return False


def _generate_optimized_timeseries_html(
    ts_id: str,
    src: Path,
    step_indices: list[int],
    field: str,
    fields_attr: str,
    figures_dir: Path,
    style: dict,
    caption: str = "",
) -> None:
    """Generate composite HTML for timeseries with identical mesh (simplified approach).

    Strategy: Generate individual frame HTMLs then create a composite viewer that
    loads them via iframes in a grid, reducing redundancy in the manifest/Lua layer
    while keeping the per-frame HTML generation working.
    """
    try:
        from scripts.data_loader import SimulationData

        sim = SimulationData(str(src)).load()
        available_fields = [f.strip() for f in fields_attr.split(",") if f.strip()] if fields_attr else []
        if field and field not in available_fields:
            available_fields.insert(0, field)
        if not available_fields:
            available_fields = [field]

        print(f"Generating optimized timeseries for {ts_id}…", file=sys.stderr)

        # Generate individual frame HTMLs using existing function
        frame_ids = []
        total_size = 0
        for frame_idx, time_idx in enumerate(step_indices):
            frame_id = f"{ts_id}-frame-{frame_idx}"
            frame_ids.append(frame_id)

            out_html = figures_dir / f"{frame_id}.html"
            if not is_cache_valid(out_html, src, extra_deps=[]):
                print(f"  Generating {frame_id}…", file=sys.stderr)
                try:
                    generate_html_figure(
                        src, field, str(time_idx), out_html,
                        fig_id=frame_id, available_fields=available_fields,
                        background=style["background"],
                        axis_color=style["axis_color"],
                        cmap=style["cmap"],
                        decimate="auto",
                    )
                except Exception as exc:
                    print(f"ERROR generating frame {frame_id}: {exc}", file=sys.stderr)
                    raise

            frame_size = out_html.stat().st_size
            total_size += frame_size
            print(f"    {frame_id}: {frame_size//1024} KB", file=sys.stderr)

        # Generate composite viewer HTML
        composite_html = _build_timeseries_composite_html(
            ts_id=ts_id,
            frame_ids=frame_ids,
            step_indices=step_indices,
            available_fields=available_fields,
            caption=caption,
        )

        output_path = figures_dir / f"{ts_id}.html"
        output_path.write_text(composite_html, encoding='utf-8')

        composite_size = output_path.stat().st_size
        print(f"Generated composite timeseries: {output_path} ({composite_size//1024} KB)", file=sys.stderr)
        print(f"  Total: {(total_size + composite_size)//1024} KB", file=sys.stderr)

    except Exception as exc:
        print(f"ERROR generating optimized timeseries {ts_id}: {exc}", file=sys.stderr)
        raise


def _build_timeseries_composite_html(
    ts_id: str,
    frame_ids: list[str],
    step_indices: list[int],
    available_fields: list[str],
    caption: str = "",
) -> str:
    """Build composite HTML for timeseries with iframe grid layout."""

    frames_html = "\n".join(
        f'    <div class="frame-container">'
        f'      <iframe src="/state/figures/{fid}.html" frameborder="0" class="frame-iframe"></iframe>'
        f'      <div class="frame-label">Frame {i} (t={step_indices[i]})</div>'
        f'    </div>'
        for i, fid in enumerate(frame_ids)
    )

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Timeseries: {ts_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0d1117; color: #c9d1d9; }}
        .container {{ display: flex; flex-direction: column; height: 100vh; }}
        .header {{ padding: 16px; background: #161b22; border-bottom: 1px solid #30363d; }}
        .header h1 {{ font-size: 24px; margin-bottom: 4px; }}
        .header p {{ font-size: 13px; color: #8b949e; }}
        .controls {{ padding: 12px 16px; background: #0d1117; border-bottom: 1px solid #30363d; display: flex; gap: 16px; align-items: center; }}
        .control-group {{ display: flex; gap: 8px; align-items: center; }}
        .control-group label {{ font-size: 13px; display: flex; align-items: center; gap: 6px; }}
        select {{ padding: 6px 10px; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; font-size: 12px; }}
        .grid-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 8px;
            flex: 1;
            overflow: auto;
            padding: 8px;
            background: #010409;
        }}
        .frame-container {{
            position: relative;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .frame-iframe {{
            flex: 1;
            min-height: 400px;
            border: none;
        }}
        .frame-label {{
            padding: 8px 12px;
            background: #0d1117;
            border-top: 1px solid #30363d;
            font-size: 12px;
            color: #8b949e;
            font-family: monospace;
        }}
        .sync-btn {{
            padding: 6px 12px;
            background: #238636;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
        }}
        .sync-btn:hover {{ background: #2ea043; }}
        .sync-btn.active {{ background: #1f6feb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{ts_id}</h1>
            {f'<p>{caption}</p>' if caption else ''}
        </div>

        <div class="controls">
            <div class="control-group">
                <label for="fieldSelect">Field:</label>
                <select id="fieldSelect">
                    {chr(10).join(f'                    <option value="{f}">{f}</option>' for f in available_fields)}
                </select>
            </div>
            <button id="syncBtn" class="sync-btn">Sync Cameras (Off)</button>
        </div>

        <div class="grid-container" id="gridContainer">
{frames_html}
        </div>
    </div>

    <script>
        const FRAME_IDS = {json.dumps(frame_ids)};
        const AVAILABLE_FIELDS = {json.dumps(available_fields)};

        let syncCameras = false;
        let viewers = [];

        function getAllViewers() {{
            return Array.from(document.querySelectorAll('.frame-iframe')).map(
                (iframe) => iframe.contentWindow
            ).filter(Boolean);
        }}

        document.getElementById('syncBtn').addEventListener('click', (e) => {{
            syncCameras = !syncCameras;
            e.target.textContent = `Sync Cameras (${{syncCameras ? 'On' : 'Off'}})`;
            e.target.classList.toggle('active', syncCameras);
            console.log('Sync cameras:', syncCameras);
        }});

        document.getElementById('fieldSelect').addEventListener('change', (e) => {{
            const field = e.target.value;
            console.log('Field changed to:', field);

            // Propagate field change to all iframe viewers
            getAllViewers().forEach((viewerWindow) => {{
                if (viewerWindow && viewerWindow.parent !== viewerWindow) {{
                    // Try to trigger field change in the viewer
                    // This is a placeholder - real implementation would use postMessage
                    try {{
                        const fieldSelect = viewerWindow.document.getElementById('cs-field-sel-' + FRAME_IDS[0]);
                        if (fieldSelect) {{
                            fieldSelect.value = field;
                            fieldSelect.dispatchEvent(new Event('change'));
                        }}
                    }} catch (e) {{
                        // Cross-origin or not ready
                    }}
                }}
            }});
        }});

        // Setup camera sync via postMessage
        window.addEventListener('message', (e) => {{
            if (!syncCameras || e.data.type !== '4dpaper-camera') return;

            getAllViewers().forEach((viewerWindow) => {{
                if (viewerWindow && viewerWindow !== e.source) {{
                    viewerWindow.postMessage({{
                        type: '4dpaper-camera-apply',
                        camera: e.data.camera
                    }}, '*');
                }}
            }});
        }});

        console.log('Timeseries composite loaded with', FRAME_IDS.length, 'frames');
    </script>
</body>
</html>'''


def is_cache_valid(
    fig_path: Path,
    src_path: Path,
    camera_path: Path | None = None,
    field_path: Path | None = None,
    extra_deps: list[Path] | None = None,
) -> bool:
    """Return `True` when the cached figure is newer than its dependencies."""
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
    for dep in (extra_deps or []):
        if dep.exists() and fig_mtime <= dep.stat().st_mtime:
            return False
    return True


def load_styles(path: Path) -> dict:
    """Load `_4dpaper_styles.yml` or return `{}`."""
    if not path.exists():
        return {}
    try:
        import yaml
        with path.open() as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            print(f"WARNING: {path} is not a YAML mapping — ignoring styles.", file=sys.stderr)
            return {}
        return data
    except Exception as exc:
        print(f"WARNING: could not load {path}: {exc} — ignoring styles.", file=sys.stderr)
        return {}


def resolve_style(styles_config: dict, style_name: str, field_name: str) -> dict:
    """Resolve `background`, `axis_color`, and `cmap` from the style config."""
    _HARD = {"background": "white", "axis_color": "black", "cmap": "coolwarm"}

    defaults = styles_config.get("defaults", {}) if styles_config else {}
    styles   = styles_config.get("styles",   {}) if styles_config else {}

    resolved = {
        "background": defaults.get("background", _HARD["background"]),
        "axis_color": defaults.get("axis_color", _HARD["axis_color"]),
        "cmap":       defaults.get("cmap",       _HARD["cmap"]),
    }

    if style_name:
        if style_name not in styles:
            print(
                f"WARNING: style '{style_name}' not found in styles config — using defaults.",
                file=sys.stderr,
            )
        else:
            tmpl = styles[style_name]
            if "background"  in tmpl: resolved["background"]  = tmpl["background"]
            if "axis_color"  in tmpl: resolved["axis_color"]  = tmpl["axis_color"]
            if "cmap"        in tmpl: resolved["cmap"]        = tmpl["cmap"]
            field_cmaps = tmpl.get("fields", {})
            if field_name and field_name in field_cmaps:
                resolved["cmap"] = field_cmaps[field_name]

    if resolved["background"] == "transparent":
        resolved["background"] = "white"

    return resolved


def _apply_camera_from_dict(pl, fig_id: str, camera_data: dict | None) -> None:
    """Apply camera data from a dict."""
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
    """Apply saved camera state to a plotter."""
    if camera_path is None or not camera_path.exists():
        pl.isometric_view()
        return

    try:
        cam_data = json.loads(camera_path.read_text())
        pl.camera.position = cam_data["position"]
        pl.camera.focal_point = cam_data["focal_point"]
        pl.camera.up = cam_data["view_up"]

        if "parallel_scale" in cam_data and cam_data["parallel_scale"] is not None:
            pl.camera.parallel_scale = float(cam_data["parallel_scale"])
            print(f"Applied saved camera for {fig_id} (scale={pl.camera.parallel_scale:.4f})")
        else:
            print(f"Applied saved camera for {fig_id}")

        is_parallel = cam_data.get("parallel_projection", 0) == 1
        pl.camera.parallel_projection = is_parallel

    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"Warning: could not apply camera for {fig_id}: {exc}. Falling back to isometric.")
        pl.isometric_view()


_GOLDEN_TOPBAR_JS = '  function _b64ToF32(b64){if(!b64)return null;var bin=atob(b64),len=bin.length,bytes=new Uint8Array(len);for(var i=0;i<len;i++)bytes[i]=bin.charCodeAt(i);return new Float32Array(bytes.buffer);}\n  function _getDecodedField(name){if(!_decodedFieldData[name]&&FIELD_DATA[name])_decodedFieldData[name]=_b64ToF32(FIELD_DATA[name]);return _decodedFieldData[name]||null;}\n  function _getDecodedTime(name){if(!_decodedTimeData[name]){var src=TIME_DATA[name]||[];_decodedTimeData[name]=src.map(_b64ToF32);}return _decodedTimeData[name]||[];}\n  function _getTimeRange(name){return TIME_GLOBAL_RANGE[name]||[0.0,1.0];}\n  function _getRenderer(){if(_renderer&&_renderer.getActors)return _renderer;var rw=window.renderWindow;if(rw&&rw.getRenderers){var rs=rw.getRenderers();for(var i=0;i<rs.length;i++){var r=rs[i];if(r&&r.getActors&&r.getActors().length>0){_renderer=r;return r;}}for(var j=0;j<rs.length;j++){if(rs[j]){_renderer=rs[j];return _renderer;}}}return null;}\n  function _findMeshActor(){if(!window.__4dp_global_probe){window.__4dp_global_probe=true;var hits=Object.keys(window).filter(function(k){return /vtk|render|view|trame|scene|loca/i.test(k);});hits.forEach(function(k){try{var v=window[k];}catch(_){}});var canvases=document.querySelectorAll("canvas");canvases.forEach(function(c,ci){var keys=Object.keys(c).filter(function(k){return /vtk|render/i.test(k);});});try{var pIfr=parent&&parent.window;}catch(_){}try{var olv=window.OfflineLocalView;if(olv){["getRenderer","getRenderWindow","getRenderers","getViewer","getView","render","scene","viewer"].forEach(function(m){});}}catch(e){}try{var cs=document.querySelectorAll("canvas");if(cs&&cs[0]){var c=cs[0];var ck=[];for(var key in c){if(/vtk|render/i.test(key))ck.push(key);}}}catch(_){}}var r=_getRenderer();if(!r){if(!window.__4dp_no_r){window.__4dp_no_r=true;}return null;}if(!window.__4dp_probed){window.__4dp_probed=true;var rw=window.renderWindow;var rs=rw&&rw.getRenderers?rw.getRenderers():[];rs.forEach(function(rr,ri){var acts=rr.getActors?rr.getActors():[];var props=rr.getViewProps?rr.getViewProps():[];var all=[].concat(acts).concat(props);all.forEach(function(a,ai){var m=a&&a.getMapper&&a.getMapper();var d=m&&m.getInputData&&m.getInputData();var pd=d&&d.getPointData&&d.getPointData();var arrs=[];if(pd&&pd.getNumberOfArrays){for(var k=0;k<pd.getNumberOfArrays();k++){var arr=pd.getArrayByIndex&&pd.getArrayByIndex(k);arrs.push(arr&&arr.getName&&arr.getName());}}});});}var acts=r.getActors?r.getActors():[];var props=r.getViewProps?r.getViewProps():[];var all=[].concat(acts).concat(props);for(var i=0;i<all.length;i++){var a=all[i],m=a&&a.getMapper&&a.getMapper(),d=m&&m.getInputData&&m.getInputData();if(d&&d.getPointData&&d.getPointData())return a;}return null;}\n  function _getScalarTarget(){_meshActor=_meshActor||_findMeshActor();if(!_meshActor){return null;}var mapper=_meshActor.getMapper&&_meshActor.getMapper();var input=mapper&&mapper.getInputData&&mapper.getInputData();var pd=input&&input.getPointData&&input.getPointData();var scalars=pd&&pd.getScalars&&pd.getScalars();if(!mapper||!input||!pd||!scalars){return null;}return {mapper:mapper,input:input,pd:pd,scalars:scalars};}\n  function _applyScalarArray(arr,range,name){var t=_getScalarTarget();if(!t||!arr){return false;}var next=t.pd&&t.pd.getArrayByName?t.pd.getArrayByName(_displayScalarName):null;if(next&&next.setData){next.setData(arr,1);}else if(t.pd&&t.pd.getScalars&&t.pd.getScalars()&&t.pd.getScalars().setData){next=t.pd.getScalars();next.setData(arr,1);}else if(t.scalars&&t.scalars.newClone){next=t.scalars.newClone();if(next.setNumberOfComponents)next.setNumberOfComponents(1);if(next.setData)next.setData(arr,1);}else if(t.scalars&&t.scalars.newInstance){next=t.scalars.newInstance({numberOfComponents:1,values:arr});}else {return false;}if(next&&next.setName)next.setName(_displayScalarName);if(next&&t.pd.addArray)t.pd.addArray(next);if(_displayScalarName&&t.pd.setActiveScalars)t.pd.setActiveScalars(_displayScalarName);if(next&&t.pd.setScalars)t.pd.setScalars(next);if(next&&next.modified)next.modified();if(t.pd.modified)t.pd.modified();if(t.input.modified)t.input.modified();if(t.mapper.setColorByArrayName)t.mapper.setColorByArrayName(_displayScalarName);if(t.mapper.setScalarModeToUsePointData)t.mapper.setScalarModeToUsePointData();if(t.mapper.setScalarVisibility)t.mapper.setScalarVisibility(true);if(range&&t.mapper.setScalarRange)t.mapper.setScalarRange(range[0],range[1]);if(t.mapper.mapScalars)t.mapper.mapScalars(t.input,1.0);if(t.mapper.modified)t.mapper.modified();if(_meshActor.modified)_meshActor.modified();var _sbrw=window.renderWindow;if(_sbrw&&_sbrw.getRenderers){var _sbrs=_sbrw.getRenderers();for(var _sbi=0;_sbi<_sbrs.length;_sbi++){var _sbp=[].concat(_sbrs[_sbi].getActors?_sbrs[_sbi].getActors():[]).concat(_sbrs[_sbi].getViewProps?_sbrs[_sbi].getViewProps():[]);for(var _sbj=0;_sbj<_sbp.length;_sbj++){var _sba=_sbp[_sbj];if(_sba.getClassName&&_sba.getClassName().indexOf(\'ScalarBar\')>=0){if(name&&_sba.setAxisLabel)_sba.setAxisLabel(name);var _sbl=_sba.getScalarsToColors&&_sba.getScalarsToColors();if(_sbl&&range&&_sbl.setMappingRange){_sbl.setMappingRange(range[0],range[1]);if(_sbl.updateRange)_sbl.updateRange();}if(_sba.modified)_sba.modified();}}}}if(window.renderWindow){window.renderWindow.render();}return true;}\n  function _emitTimeSync(){if(TIME_DATA[ACTIVE_FIELD]&&TIME_DATA[ACTIVE_FIELD].length>1)parent.postMessage({type:"4dpaper-time",fig_id:FIG_ID,idx:_timeIdx,playing:_timePlaying},"*");}\n  function _setTimeFrame(idx,silent){var frames=_getDecodedTime(ACTIVE_FIELD);if(!frames||idx<0||idx>=frames.length){return;}_timeIdx=idx;var slider=document.getElementById("cs-time-slider-__FIGSAFE__");if(slider)slider.value=String(idx);var label=document.getElementById("cs-time-val-__FIGSAFE__");if(label)label.textContent=(TIME_LABELS[idx]||String(idx));var arr=frames[idx];if(arr)_applyScalarArray(arr,_getTimeRange(ACTIVE_FIELD),ACTIVE_FIELD);if(!silent)_emitTimeSync();}\n  function _setPlaying(v,silent){_timePlaying=!!v;var btn=document.getElementById("cs-play-__FIGSAFE__");if(btn)btn.innerHTML=_timePlaying?"&#x23F8;":"&#x25B6;";if(!_timePlaying&&_timeRaf){cancelAnimationFrame(_timeRaf);_timeRaf=0;}if(!silent)_emitTimeSync();}\n  function _tickTime(ts){if(!_timePlaying)return;if(!_timeLastTs)_timeLastTs=ts;if(ts-_timeLastTs>=180){var frames=_getDecodedTime(ACTIVE_FIELD);if(frames&&frames.length){_setTimeFrame((_timeIdx+1)%frames.length);} _timeLastTs=ts;}_timeRaf=requestAnimationFrame(_tickTime);}\n  function _bindControls(){if(_controlsBound)return;_controlsBound=true;var slider=document.getElementById("cs-time-slider-__FIGSAFE__");if(slider)slider.addEventListener("input",function(){_setPlaying(false,true);_setTimeFrame(parseInt(this.value||"0",10)||0);});var play=document.getElementById("cs-play-__FIGSAFE__");if(play)play.addEventListener("click",function(){if(_locked){if(typeof _showLockedBadge==="function")_showLockedBadge();return;}var nv=!_timePlaying;_setPlaying(nv);_timeLastTs=0;if(nv)_timeRaf=requestAnimationFrame(_tickTime);});var fieldSel=document.getElementById("cs-field-sel-__FIGSAFE__");if(fieldSel)fieldSel.addEventListener("change",function(){var f=this.value,arr=_getDecodedField(f),range=FIELD_RANGES[f];if(arr&&_applyScalarArray(arr,range,f)){ACTIVE_FIELD=f;var badge=document.getElementById("cs-field-badge-__FIGSAFE__");if(badge){badge.textContent=f;badge.style.display="inline-block";badge.style.background="rgba(74,158,255,0.18)";badge.style.color="#9ecbff";setTimeout(function(){badge.style.display="none";},900);}if(TIME_DATA[f]&&TIME_DATA[f].length>_timeIdx){_setTimeFrame(_timeIdx);}}});if(TIME_DATA[ACTIVE_FIELD]&&TIME_DATA[ACTIVE_FIELD].length>1){var label=document.getElementById("cs-time-val-__FIGSAFE__");if(label)label.textContent=(TIME_LABELS[_timeIdx]||String(_timeIdx));}}\n  function _setLocked(v){\n    _locked=v;if(v){_setPlaying(false);}\n    var w=document.getElementById("cs-lock-widget-__FIGSAFE__");\n    if(w)w.innerHTML=v?"&#x1F512;":"&#x1F513;";\n    var s=document.getElementById("cs-lock-shield-__FIGSAFE__");\n    if(s)s.style.display=v?"block":"none";\n    var rw=window.renderWindow;\n    var i=(rw&&rw.getInteractor?rw.getInteractor():null);\n    if(i&&i.setEnabled)i.setEnabled(v?0:1);\n    var c=_cont||(i&&i.getContainer?i.getContainer():null);\n    if(c&&c.style){c.style.pointerEvents=v?"none":"";c.style.touchAction=v?"none":"";}\n    if(v&&i&&i.stopAnimating)i.stopAnimating();\n  }\n  function _n3(v){var l=Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);return l<1e-10?[0,0,1]:[v[0]/l,v[1]/l,v[2]/l];}\n  function _cr(a,b){return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}\n  function _dt(a,b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}\n  function _rot(v,ax,deg){var a=_n3(ax),x=v[0],y=v[1],z=v[2],c=Math.cos(deg*Math.PI/180),s=Math.sin(deg*Math.PI/180),d=a[0]*x+a[1]*y+a[2]*z;return[x*c+(a[1]*z-a[2]*y)*s+a[0]*d*(1-c),y*c+(a[2]*x-a[0]*z)*s+a[1]*d*(1-c),z*c+(a[0]*y-a[1]*x)*s+a[2]*d*(1-c)];}\n  window.csSetView___FIGSAFE__=function(dir,vup){if(!_renderer || _locked)return;var cam=_renderer.getActiveCamera(),fp=cam.getFocalPoint(),dist=cam.getDistance(),pn=_n3(dir),up=vup?_n3(vup):((Math.abs(pn[2])>0.9)?[0,1,0]:[0,0,1]);cam.setPosition(fp[0]+pn[0]*dist,fp[1]+pn[1]*dist,fp[2]+pn[2]*dist);cam.setViewUp(up[0],up[1],up[2]);cam.setFocalPoint(fp[0],fp[1],fp[2]);_renderer.resetCameraClippingRange();if(window.renderWindow)window.renderWindow.render();_sendCam(_renderer);};\n  window.csRotate___FIGSAFE__=function(dx,dy){if(!_renderer || _locked)return;var cam=_renderer.getActiveCamera(),pos=cam.getPosition(),fp=cam.getFocalPoint(),vup=cam.getViewUp(),rel=[pos[0]-fp[0],pos[1]-fp[1],pos[2]-fp[2]],right=_n3(_cr(rel,vup)),pitch=_rot(rel,right,dy),yawAxis=_n3(vup),yaw=_rot(pitch,yawAxis,dx);cam.setPosition(fp[0]+yaw[0],fp[1]+yaw[1],fp[2]+yaw[2]);cam.setViewUp(vup[0],vup[1],vup[2]);_renderer.resetCameraClippingRange();if(window.renderWindow)window.renderWindow.render();_sendCam(_renderer);};\n  var _camTimer=null;\n  function _sendCam(r){if(_locked)return;clearTimeout(_camTimer);_camTimer=setTimeout(function(){var c=r.getActiveCamera();var d={position:c.getPosition(),focal_point:c.getFocalPoint(),view_up:c.getViewUp(),parallel_scale:c.getParallelScale(),parallel_projection:c.getParallelProjection()?1:0};parent.postMessage({type:"4dpaper-camera",fig_id:FIG_ID,camera:d},"*");},300);}\n  var _svg=null;\n  function _drawAxes(){if(!_renderer||!_svg)return;var cam=_renderer.getActiveCamera(),pos=cam.getPosition(),fp=cam.getFocalPoint(),vup=cam.getViewUp(),vd=_n3([fp[0]-pos[0],fp[1]-pos[1],fp[2]-pos[2]]),right=_n3(_cr(vd,vup)),up=_cr(right,vd),cx=28,cy=28,R=22;function proj(v){return[cx+R*_dt(v,right),cy-R*_dt(v,up)];}var axes=[{w:[1,0,0],col:"#ff6666",lcol:"#ff9999",lbl:"X",hpd:\'data-dir="1,0,0"\'},{w:[0,1,0],col:"#66cc66",lcol:"#99cc99",lbl:"Y",hpd:\'data-dir="0,1,0"\'},{w:[0,0,1],col:"#6699ff",lcol:"#99aaff",lbl:"Z",hpd:\'data-dir="0,0,1"\'}];var h="";axes.forEach(function(ax){var tip=proj(ax.w),tx=tip[0].toFixed(1),ty=tip[1].toFixed(1),dx=tip[0]-cx,dy=tip[1]-cy,len=Math.sqrt(dx*dx+dy*dy)||1,nx=-dy/len*3.5,ny=dx/len*3.5,bx1=(tip[0]-dx/len*7+nx).toFixed(1),by1=(tip[1]-dy/len*7+ny).toFixed(1),bx2=(tip[0]-dx/len*7-nx).toFixed(1),by2=(tip[1]-dy/len*7-ny).toFixed(1);h+=\'<line x1="\'+cx+\'" y1="\'+cy+\'" x2="\'+tx+\'" y2="\'+ty+\'" \'+ax.hpd+\' stroke="\'+ax.col+\'" stroke-width="2.5"/>\';h+=\'<polygon points="\'+tx+","+ty+" "+bx1+","+by1+" "+bx2+","+by2+\'" \'+ax.hpd+\' fill="\'+ax.col+\'"/>\';h+=\'<text x="\'+(tip[0]+dx/len*5).toFixed(1)+\'" y="\'+(tip[1]+dy/len*5+3).toFixed(1)+\'" \'+ax.hpd+\' font-size="9" fill="\'+ax.lcol+\'" font-family="monospace">\'+ax.lbl+\'</text>\';});_svg.innerHTML=h;}\n  function _axLoop(){_drawAxes();requestAnimationFrame(_axLoop);}\n  (function _wR(){\n    var rw=window.renderWindow;\n    var r=_getRenderer();\n    if(r){\n          var i=rw&&rw.getInteractor?rw.getInteractor():null;_cont=i?i.getContainer():null;\n          if(_cont){\n            _cont.addEventListener("mouseenter",function(){_isHovered=true;window.focus();});\n            _cont.addEventListener("mouseleave",function(){_isHovered=false;});\n            _cont.addEventListener("wheel",function(e){e.preventDefault();},{passive:false});\n          }\n          _bindControls();\n          _svg=document.getElementById("cs-svg-axes-__FIGSAFE__");_svg.addEventListener("click",function(e){var dv=e.target.getAttribute("data-dir");if(!dv)return;if(_locked){if(typeof _showLockedBadge==="function")_showLockedBadge();return;}csSetView___FIGSAFE__(dv.split(",").map(Number));});_axLoop();\n          if(TIME_DATA[ACTIVE_FIELD]&&TIME_DATA[ACTIVE_FIELD].length>1)_setTimeFrame(_timeIdx);\n          document.addEventListener("pointerup",function(){_sendCam(_renderer);});\n          document.addEventListener("mouseup",function(){_sendCam(_renderer);});\n          document.addEventListener("touchend",function(){_sendCam(_renderer);});\n          window.addEventListener("message",function(e){\n            if(!e.data)return;var d=e.data;\n            if(d.type==="4dpaper-camera-apply"){if(_locked)return;var r=_getRenderer();if(!r)return;var cam=d.camera,c=r.getActiveCamera();if(cam.position)c.setPosition(cam.position[0],cam.position[1],cam.position[2]);if(cam.focal_point)c.setFocalPoint(cam.focal_point[0],cam.focal_point[1],cam.focal_point[2]);if(cam.view_up)c.setViewUp(cam.view_up[0],cam.view_up[1],cam.view_up[2]);if(cam.parallel_scale!=null)c.setParallelScale(cam.parallel_scale);if(cam.parallel_projection!=null)c.setParallelProjection(!!cam.parallel_projection);window.renderWindow.render();}\n            else if(d.type==="4dpaper-time-apply"&&d.fig_id!==FIG_ID){_setPlaying(!!d.playing,true);_timeLastTs=0;_setTimeFrame(parseInt(d.idx||"0",10)||0,true);}\n            else if(d.type==="4dpaper-lock-state"&&d.fig_id===FIG_ID)_setLocked(!!d.locked);\n            else if(d.type==="4dpaper-lock-ack"&&d.fig_id===FIG_ID){if(d.status!=="ok")_setLocked(!_locked);}\n            else if(d.type==="4dpaper-lock-all")_setLocked(!!d.locked);\n            else if(d.type==="4dpaper-hide-lock-btn"){var w=document.getElementById("cs-lock-widget-__FIGSAFE__");if(w)w.style.display="none";var s=document.getElementById("cs-lock-sep-__FIGSAFE__");if(s)s.style.display="none";}\n          });\n          return;\n    }\n    setTimeout(_wR,200);\n  })();\n  _bindControls();\n  window.addEventListener("keydown",function(e){if(!_renderer||!_isHovered||_locked)return;var k=e.key.toLowerCase();if(k==="x")csSetView___FIGSAFE__([1,0,0],[0,0,1]);else if(k==="y")csSetView___FIGSAFE__([0,1,0],[0,0,1]);else if(k==="z")csSetView___FIGSAFE__([0,0,1],[0,1,0]);else if(k==="i")csSetView___FIGSAFE__([1,1,1],[0,0,1]);else if(e.key==="ArrowUp")csRotate___FIGSAFE__(0,-90);else if(e.key==="ArrowDown")csRotate___FIGSAFE__(0,90);else if(e.key==="ArrowLeft")csRotate___FIGSAFE__(-90,0);else if(e.key==="ArrowRight")csRotate___FIGSAFE__(90,0);if(e.key.startsWith("Arrow"))e.preventDefault();});'

_GOLDEN_TOPBAR_JS = _GOLDEN_TOPBAR_JS.replace(
    """var _camTimer=null;
  function _sendCam(r){if(_locked)return;clearTimeout(_camTimer);_camTimer=setTimeout(function(){var c=r.getActiveCamera();var d={position:c.getPosition(),focal_point:c.getFocalPoint(),view_up:c.getViewUp(),parallel_scale:c.getParallelScale(),parallel_projection:c.getParallelProjection()?1:0};parent.postMessage({type:"4dpaper-camera",fig_id:FIG_ID,camera:d},"*");},300);}
""",
    """var _camLastSent=0;
  function _postCam(r){var c=r.getActiveCamera();var d={position:c.getPosition(),focal_point:c.getFocalPoint(),view_up:c.getViewUp(),parallel_scale:c.getParallelScale(),parallel_projection:c.getParallelProjection()?1:0};parent.postMessage({type:"4dpaper-camera",fig_id:FIG_ID,camera:d},"*");}
  function _sendCam(r){if(_locked)return;var now=Date.now();if(now-_camLastSent<40)return;_camLastSent=now;_postCam(r);}
""",
)


def _controls_strip_snippet(
    fig_id: str,
    show_lock_btn: bool = True,
    show_orientation: bool = True,
    fields_to_embed: list[str] | None = None,
    active_field: str = "",
    field_data_b64: dict | None = None,
    field_ranges: dict | None = None,
    time_labels: list[str] | None = None,
    time_data_b64: dict | None = None,
    time_global_range: dict | None = None,
    time_idx: int = 0,
    time_field: str = "",
) -> str:
    """Return the golden top-bar HTML + IIFE JS for one figure.

    Reproduces the May-2026 reference figure UI: a fixed 26px top bar with an
    inline field selector, play/pause button, time slider + value, and a
    bottom-left axis widget. Lock state is driven externally via postMessage
    (panel lock-all / dashboard), matching the reference figures.

    `time_data_b64` and `time_global_range` are per-field dicts
    (``{field: [b64_frame, ...]}`` and ``{field: [min, max]}``) so the field
    switcher animates the correct field while playing.
    """
    fig_id_safe = fig_id.replace("</", "").replace('"', "").replace("-", "_")

    fields = list(fields_to_embed or ([active_field] if active_field else []))
    has_fields = len(fields) > 1

    tdata = time_data_b64 if isinstance(time_data_b64, dict) else {}
    tglobal = time_global_range if isinstance(time_global_range, dict) else {}
    active_frames = tdata.get(active_field or time_field) or []
    has_time = bool(time_labels and len(time_labels) > 1 and len(active_frames) > 1)
    n_time = len(active_frames)

    # Nothing to render (e.g. plotly graph): emit no markup and no JS so we
    # never inject a vtk renderer-polling loop into a non-vtk page.
    if not has_fields and not has_time and not show_orientation:
        return ""

    # ── Top bar markup ───────────────────────────────────────────────────────
    topbar = ""
    if has_fields or has_time or show_lock_btn:
        inner = ""
        if has_fields:
            opts = "".join(
                f'<option value="{f}"{" selected" if f == active_field else ""}'
                ' style="background:#1c1c28;color:#ddd;">' + f + '</option>'
                for f in fields
            )
            inner += (
                '<label style="display:flex;align-items:center;gap:2px;flex-shrink:0;">'
                f'<select id="cs-field-sel-{fig_id_safe}" style="background:transparent;'
                'border:none;color:#ddd;font-family:system-ui,sans-serif;font-size:10px;'
                'cursor:pointer;outline:none;max-width:90px;padding:0 2px 0 0;'
                '-webkit-appearance:none;-moz-appearance:none;appearance:none;">'
                f'{opts}</select>'
                '<span style="color:#777;font-size:8px;flex-shrink:0;'
                'pointer-events:none;margin-left:-3px;">&#9662;</span></label>'
                '<span style="width:1px;height:14px;background:rgba(255,255,255,0.15);'
                'flex-shrink:0;display:inline-block;"></span>'
            )
        if has_time:
            init_label = time_labels[time_idx] if time_idx < len(time_labels) else str(time_idx)
            inner += (
                f'<button id="cs-play-{fig_id_safe}" title="Play / pause animation" '
                'style="background:none;border:none;cursor:pointer;color:#ccc;font-size:11px;'
                'flex-shrink:0;padding:0 1px;line-height:1;">&#x25B6;</button>'
                '<span style="color:#777;font-size:9px;flex-shrink:0;">t</span>'
                f'<input type="range" id="cs-time-slider-{fig_id_safe}" min="0" '
                f'max="{n_time - 1}" value="{time_idx}" style="flex:1;min-width:30px;'
                'max-width:110px;cursor:pointer;accent-color:#4a9eff;margin:0;">'
                f'<span id="cs-time-val-{fig_id_safe}" style="color:#aaa;font-size:9px;'
                'flex-shrink:0;white-space:nowrap;font-family:monospace;">'
                f'{init_label}</span>'
            )
        inner += (
            f'<span id="cs-field-badge-{fig_id_safe}" style="display:none;padding:1px 4px;'
            'border-radius:2px;font-size:9px;flex-shrink:0;"></span>'
        )
        if show_lock_btn:
            inner += (
                f'<span id="cs-lock-cluster-{fig_id_safe}" style="margin-left:auto;display:flex;'
                'align-items:center;gap:6px;flex-shrink:0;">'
                f'<span id="cs-cam-sync-{fig_id_safe}" title="The saved camera is used for static PDF screenshots." '
                'style="display:none;padding:1px 6px;border-radius:999px;font-size:9px;'
                'line-height:1.4;font-family:system-ui,sans-serif;"></span>'
                f'<button id="cs-lock-widget-{fig_id_safe}" title="Lock / unlock camera" '
                'style="background:none;border:none;cursor:pointer;'
                'color:#ccc;font-size:12px;flex-shrink:0;padding:0 2px;line-height:1;">'
                '&#x1F513;</button>'
                '</span>'
            )
        topbar = (
            f'<div id="cs-topbar-{fig_id_safe}" style="position:fixed;top:0;left:0;right:0;'
            'z-index:9999;display:flex;align-items:center;gap:5px;'
            'background:rgba(18,18,26,0.82);border-bottom:1px solid rgba(255,255,255,0.09);'
            f'padding:0 6px;height:26px;box-sizing:border-box;">{inner}</div>'
        )

    corner = ""
    if show_orientation:
        corner = (
            f'<div id="cs-corner-{fig_id_safe}" style="position:fixed;bottom:4px;left:4px;'
            'z-index:9999;display:flex;align-items:center;gap:6px;">'
            f'<svg id="cs-svg-axes-{fig_id_safe}" width="56" height="56" '
            'style="background:transparent;border:none;border-radius:0;display:block;'
            'cursor:pointer;overflow:visible;" '
            'title="Click axis tip: ortho view \u00b7 Click axis tail: opposite view"></svg>'
            f'<span id="cs-iso-flash-{fig_id_safe}" style="font-size:9px;color:#ffe033;'
            'font-family:monospace;min-width:60px;"></span></div>'
        )

    if show_lock_btn:
        html_block_lock = (
            f'<div id="cs-lock-shield-{fig_id_safe}" style="display:none;position:fixed;'
            'inset:0;z-index:9998;cursor:not-allowed;"></div>'
        )
    else:
        html_block_lock = ""
    html_block = topbar + corner + html_block_lock

    # ── Data header + golden IIFE body ───────────────────────────────────────
    fid = json.dumps(fig_id).replace("</", "<\\/")
    af = json.dumps(active_field or time_field).replace("</", "<\\/")
    fd = json.dumps(field_data_b64 or {}).replace("</", "<\\/")
    fr = json.dumps(field_ranges or {})
    td = json.dumps(tdata).replace("</", "<\\/")
    tl = json.dumps(time_labels or [])
    tgr = json.dumps(tglobal)
    header = (
        "  var FIG_ID=" + fid + ", _locked=false, _renderer=null, _isHovered=false, "
        "_cont=null, _meshActor=null, _controlsBound=false, _timeIdx=" + str(int(time_idx))
        + ", _timePlaying=false, _timeRaf=0, _timeLastTs=0, "
        '_displayScalarName="__4dpaper_display__";\n'
        "  var ACTIVE_FIELD=" + af + ", FIELD_DATA=" + fd + ", FIELD_RANGES=" + fr
        + ", TIME_DATA=" + td + ", TIME_LABELS=" + tl + ", TIME_GLOBAL_RANGE=" + tgr
        + ", _decodedFieldData={}, _decodedTimeData={};\n"
    )

    js_body = _GOLDEN_TOPBAR_JS.replace("__FIGSAFE__", fig_id_safe)
    # Lock widget wiring (relay.js handles 4dpaper-lock-query / 4dpaper-lock-toggle).
    # _setLocked / _locked / FIG_ID live in the IIFE body above this snippet.
    lock_js = ""
    if show_lock_btn:
        lock_js = (
            '\n  function _setCamSyncStatus(state){var _cs=document.getElementById("cs-cam-sync-' + fig_id_safe + '");'
            'if(!_cs)return;'
            'if(state==="syncing"){_cs.style.display="inline-block";_cs.textContent="Syncing…";'
            '_cs.style.background="rgba(255,204,77,0.16)";_cs.style.color="#ffe08a";'
            '_cs.title="Saving the current camera for PDF export.";return;}'
            'if(state==="ok"){_cs.style.display="inline-block";_cs.textContent="Camera synced";'
            '_cs.style.background="rgba(76,175,80,0.16)";_cs.style.color="#9ee6a3";'
            '_cs.title="The saved camera is used for static PDF screenshots.";return;}'
            'if(state==="error"){_cs.style.display="inline-block";_cs.textContent="Sync failed";'
            '_cs.style.background="rgba(244,67,54,0.16)";_cs.style.color="#ffb3ad";'
            '_cs.title="Camera sync failed. PDF export will keep the last saved view.";return;}'
            '_cs.style.display="none";}'
            '\n  var _origSendCam=_sendCam;'
            '_sendCam=function(r){_setCamSyncStatus("syncing");_origSendCam(r);};'
            '\n  window.addEventListener("message",function(e){'
            'if(!e.data)return;var d=e.data;'
            'if(d.type==="4dpaper-camera-ack"&&(d.fig_id===FIG_ID||d.fig_id==="*")){'
            '_setCamSyncStatus(d.status==="ok"?"ok":"error");}});'
            '\n  (function(){var _lw=document.getElementById("cs-lock-widget-' + fig_id_safe + '");'
            'if(_lw)_lw.addEventListener("click",function(){var nv=!_locked;_setLocked(nv);'
            'parent.postMessage({type:"4dpaper-lock-toggle",fig_id:FIG_ID,locked:nv},"*");});'
            'parent.postMessage({type:"4dpaper-lock-query",fig_id:FIG_ID},"*");})();'
        )
    js_block = "<script>\n(function(){\n" + header + js_body + lock_js + "\n})();\n</script>\n"
    return html_block + js_block


def _load_saved_field_state(fig_id: str, field: str, time_spec: str) -> tuple[str, str]:
    """Return the saved field/time selection for one figure when present."""
    field_state_path = _project_root / "state" / f"field_{fig_id}.json"
    next_field = field
    next_time = time_spec
    if field_state_path.exists():
        try:
            state_data = json.loads(field_state_path.read_text())
            if "field" in state_data:
                next_field = state_data["field"]
            if "time" in state_data:
                next_time = state_data["time"]
        except Exception:
            pass
    return next_field, next_time



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
    show_colorbar: bool = True,
    decimate: str = "auto",
) -> None:
    """Generate a static PNG figure with PyVista."""
    import pyvista as pv
    from scripts.data_loader import SimulationData

    sim = SimulationData(str(src_path)).load()

    if sim.n_steps == 0:
        raise RuntimeError(
            f"Simulation at {src_path} has no time steps."
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
        raise RuntimeError(f"Could not load mesh at step {idx} from {src_path}")

    surface = mesh.extract_surface(algorithm='dataset_surface')
    surface = _apply_decimation(surface, decimate, label=f"{fig_id or 'fig'}.png")

    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = background if background != "transparent" else "white"

    if field and (field in surface.point_data or field in surface.cell_data):
        pl.add_mesh(
            surface,
            scalars=field,
            cmap=cmap,
            smooth_shading=True,
            show_scalar_bar=show_colorbar,
            scalar_bar_args={"title": field, "color": axis_color} if show_colorbar else {},
        )
    else:
        pl.add_mesh(surface, color="#aaaaaa", opacity=0.9)
        print(
            f"Warning: field '{field}' not found — rendering geometry only.",
            file=sys.stderr,
        )

    # Apply saved camera if available, else fall back to isometric view.
    _cam_id = camera_fig_id or fig_id
    camera_path = (_project_root / "state" / f"camera_{_cam_id}.json" if _cam_id else None)
    apply_camera_state(pl, _cam_id or "unnamed", camera_path)
    pl.add_axes(interactive=False, line_width=3)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.save_graphic(str(output_path.with_suffix(".pdf")))
    pl.screenshot(str(output_path))
    pl.close()
    print(f"Generated (PNG): {output_path}")


def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
    camera_fig_id: str | None = None,
    available_fields: list[str] | None = None,
    camera_preview_only: bool = False,
    background: str = "white",
    axis_color: str = "black",
    cmap: str = "coolwarm",
    show_colorbar: bool = True,
    show_lock_btn: bool = True,
    show_orientation: bool = True,
    decimate: str = "auto",
    stride: int = 1,
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
            f"Simulation at {src_path} has no time steps. "
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
        raise RuntimeError(f"Could not load mesh at step {idx} from {src_path}")

    surface = mesh.extract_surface(algorithm='dataset_surface')
    surface = _apply_decimation(surface, decimate, label=f"{fig_id or 'fig'}.html")

    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = background if background != "transparent" else "white"

    if field and (field in surface.point_data or field in surface.cell_data):
        pl.add_mesh(
            surface,
            scalars=field,
            cmap=cmap,
            smooth_shading=True,
            show_scalar_bar=show_colorbar,
            scalar_bar_args={"title": field, "color": axis_color} if show_colorbar else {},
        )
    else:
        pl.add_mesh(surface, color="#aaaaaa", opacity=0.9)
        print(
            f"Warning: field '{field}' not found in mesh — rendering geometry only.",
            file=sys.stderr,
        )

    # Apply camera — same logic as generate_png_figure so HTML and PDF start from
    # the same viewpoint.
    _cam_id = camera_fig_id or fig_id
    camera_path = (_project_root / "state" / f"camera_{_cam_id}.json" if _cam_id else None)
    apply_camera_state(pl, _cam_id or "unnamed", camera_path)

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
            print(f"Warning: field '{f}' not found — skipping from switcher.", file=sys.stderr)
            continue
        arr_f32 = arr_np.astype("float32").ravel()
        field_data_b64[f] = _b64.b64encode(arr_f32.tobytes()).decode("ascii")
        field_ranges[f] = [float(arr_f32.min()), float(arr_f32.max())]

    # ── Prepare per-field time step data blobs (one list per switchable field) ─
    # Golden top-bar schema: TIME_DATA = {field: [b64_frame, ...]} and
    # TIME_GLOBAL_RANGE = {field: [min, max]} so the field switcher animates the
    # correct field while playing. Empty string is a per-step placeholder.
    time_data_b64: dict[str, list[str]] = {}
    time_global_range: dict[str, list[float]] = {}
    time_labels: list[str] = []

    if sim.n_steps > 1 and fields_to_embed:
        step_indices = list(range(0, sim.n_steps, stride))
        print(
            f"{fig_id or 'fig'}: embedding {len(step_indices)} timesteps "
            f"(stride={stride}) × {len(fields_to_embed)} field(s) for timeline …",
            file=sys.stderr,
        )
        _tg_min: dict[str, float] = {f: float("inf") for f in fields_to_embed}
        _tg_max: dict[str, float] = {f: float("-inf") for f in fields_to_embed}
        for f in fields_to_embed:
            time_data_b64[f] = []
        import time
        for t_idx in step_indices:
            loop_start = time.time()
            # Human-readable time label (physical time value from the reader)
            if t_idx < len(sim.time_steps):
                time_labels.append(f"{sim.time_steps[t_idx]:.4g}")
            else:
                time_labels.append(str(t_idx))
            
            # 1. Load Mesh
            t_mesh = sim.get_mesh(t_idx)
            if t_mesh is None:
                for f in fields_to_embed:
                    time_data_b64[f].append("")
                continue
                
            # 2. Extract Surface
            ex_start = time.time()
            t_surface = t_mesh.extract_surface(algorithm="dataset_surface")
            ex_time = time.time() - ex_start
            
            # 3. Decimate
            dec_start = time.time()
            t_surface = _apply_decimation(t_surface, decimate, label=f"{fig_id or 'fig'} t={t_idx}")
            dec_time = time.time() - dec_start
            
            # 4. Process Arrays & Encode
            enc_start = time.time()
            t_pts = None  # lazily computed cell→point conversion, shared by all fields
            for f in fields_to_embed:
                arr_np = None
                if f in t_surface.point_data:
                    arr_np = t_surface.point_data[f]
                elif f in t_surface.cell_data:
                    if t_pts is None:
                        t_pts = t_surface.cell_data_to_point_data()
                    if f in t_pts.point_data:
                        arr_np = t_pts.point_data[f]
                if arr_np is not None:
                    arr_f32 = arr_np.astype("float32").ravel()
                    time_data_b64[f].append(_b64.b64encode(arr_f32.tobytes()).decode("ascii"))
                    _tg_min[f] = min(_tg_min[f], float(arr_f32.min()))
                    _tg_max[f] = max(_tg_max[f], float(arr_f32.max()))
                else:
                    time_data_b64[f].append("")
            enc_time = time.time() - enc_start
            
            total_time = time.time() - loop_start
            print(
                f"[{fig_id} t={t_idx}] extracted: {ex_time:.2f}s | "
                f"decimated: {dec_time:.2f}s | encoded: {enc_time:.2f}s | "
                f"total: {total_time:.2f}s", file=sys.stderr
            )
        for f in fields_to_embed:
            time_global_range[f] = (
                [_tg_min[f], _tg_max[f]] if _tg_min[f] != float("inf") else [0.0, 1.0]
            )

    # Patch viewport units so the widget has a fixed height when embedded inline.
    # PyVista's trame output uses 100vw/100vh which fills the whole page.
    html = output_path.read_text()
    html = html.replace("100vw", "900px").replace("100vh", "600px")

    if fig_id:
        if "</body>" not in html:
            print(
                f"Warning: no </body> in {output_path.name} "
                "— camera sync badge not injected.",
                file=sys.stderr,
            )
        else:
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
            html = html.replace("</body>", inj_html, 1)
    output_path.write_text(html, encoding="utf-8")
    _maybe_sign_output_html(output_path)

    print(f"Generated: {output_path}", file=sys.stderr)


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
            f"4d-panel layout must be 'COLSxROWS' (e.g. '2x2', '3x1'), got: '{layout}'"
        )
    if ncols < 1 or nrows < 1:
        raise ValueError(
            f"4d-panel layout dimensions must be positive integers, got: '{layout}'"
        )

    height = panel.get("height", "800px")

    # Generate each sub-figure HTML (reuses caching inside generate_html_figure)
    is_timeseries = panel.get("timeseries", False)
    camera_mode = panel.get("camera_mode", "independent")

    for sub_idx, sub in enumerate(panel["subfigures"]):
        src = resolve_src_path(sub["src"])
        out = figures_dir / f"{sub['id']}.html"
        af = [f.strip() for f in sub.get("fields", "").split(",") if f.strip()] or None
        saved_field, saved_time = _load_saved_field_state(sub["id"], sub["field"], sub["time"])
        camera_fig_id = panel["id"] if camera_mode == "sync" else sub["id"]
        # For timeseries: only show colorbar and lock button on the first panel
        # For sync-mode panels: never show lock button (panel-level toolbar handles it)
        is_first = sub_idx == 0
        generate_html_figure(
            src, saved_field, saved_time, out,
            fig_id=sub["id"], camera_fig_id=camera_fig_id, available_fields=af,
            show_colorbar=is_first if is_timeseries else True,
            show_lock_btn=not is_timeseries and camera_mode != "sync",
            show_orientation=is_first if is_timeseries else True,
        )

    # Bidirectional re-relay: forwards camera/field UP to top, acks DOWN to children
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
  if(e.data.type==="4dpaper-time"){{
    /* Timeseries sync: fan out time-apply to all subfigures except the sender */
    var timeSrc=e.source;
    var iframesT=document.querySelectorAll("iframe");
    var timeApply={{type:"4dpaper-time-apply",fig_id:e.data.fig_id,idx:e.data.idx,playing:e.data.playing}};
    for(var t=0;t<iframesT.length;t++){{
      if(iframesT[t].contentWindow!==timeSrc){{
        iframesT[t].contentWindow.postMessage(timeApply,"*");
      }}
    }}
  }}
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

    grid_style = (
        f'display:grid;grid-template-columns:repeat({ncols},1fr);'
        f'grid-template-rows:repeat({nrows},1fr);gap:4px;'
        f'width:100%;height:{height};background:#111;'
    )

    import base64 as _b64_panel
    cells = []
    for sub in panel["subfigures"]:
        content = (figures_dir / f"{sub['id']}.html").read_text()
        b64 = _b64_panel.b64encode(content.encode()).decode("ascii")
        cells.append(
            f'<iframe src="data:text/html;base64,{b64}" '
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
    out_path.write_text(composite, encoding="utf-8")
    _maybe_sign_output_html(out_path)
    print(f"Generated panel (HTML): {out_path}", file=sys.stderr)

    # Write manifest so Lua can embed subfigures as direct srcdoc iframes
    # (avoids data:text/html;base64 iframes which break vtk.js WebGL rendering).
    manifest = {
        "subfigures": [sub["id"] for sub in panel["subfigures"]],
        "layout": panel.get("layout", "1x1"),
        "height": panel.get("height", "800px"),
        "camera_mode": camera_mode,
    }
    manifest_path = figures_dir / f"{panel['id']}.manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    print(f"Wrote manifest: {manifest_path}", file=sys.stderr)


def generate_panel_png(panel: dict, figures_dir: Path) -> None:
    """
    Generate a composite 1920×1080 PNG composed of sub-figure PNGs in a grid.

    Layout convention: "COLSxROWS" e.g. "2x2" = 2 columns 2 rows.
    Sub-figures are arranged left-to-right, then top-to-bottom (row-major).
    Output: figures_dir/<panel-id>.png
    """
    from PIL import Image

    layout = panel["layout"]
    try:
        ncols_s, nrows_s = layout.split("x")
        ncols, nrows = int(ncols_s), int(nrows_s)
    except (ValueError, AttributeError):
        raise ValueError(
            f"4d-panel layout must be 'COLSxROWS' (e.g. '2x2', '3x1'), got: '{layout}'"
        )
    if ncols < 1 or nrows < 1:
        raise ValueError(
            f"4d-panel layout dimensions must be positive integers, got: '{layout}'"
        )

    camera_mode = panel.get("camera_mode", "independent")
    is_timeseries = panel.get("timeseries", False)
    # Generate each sub-figure PNG
    for sub_idx, sub in enumerate(panel["subfigures"]):
        src = resolve_src_path(sub["src"])
        out = figures_dir / f"{sub['id']}.png"
        saved_field, saved_time = _load_saved_field_state(sub["id"], sub["field"], sub["time"])
        cam_id = panel["id"] if camera_mode == "sync" else sub["id"]
        show_cb = (sub_idx == 0) if is_timeseries else True
        generate_png_figure(src, saved_field, saved_time, out,
                            fig_id=sub["id"], camera_fig_id=cam_id, show_colorbar=show_cb)

    # Infer canvas size from actual subfigure dimensions (no fixed 1920×1080).
    # Each cell is exactly the size of the first subfigure PNG; all subfigures
    # must have the same dimensions (they are rendered with the same window_size).
    first_img = Image.open(figures_dir / f"{panel['subfigures'][0]['id']}.png")
    cell_w, cell_h = first_img.size
    canvas_w = cell_w * ncols
    canvas_h = cell_h * nrows

    # Compose: paste each subfigure at its natural size (no scaling needed)
    canvas = Image.new("RGB", (canvas_w, canvas_h), color="white")
    for idx, sub in enumerate(panel["subfigures"]):
        row, col = divmod(idx, ncols)
        img = Image.open(figures_dir / f"{sub['id']}.png").convert("RGB")
        # Resize only if this subfigure differs from the expected cell size
        if img.size != (cell_w, cell_h):
            img = img.resize((cell_w, cell_h), Image.LANCZOS)
        canvas.paste(img, (col * cell_w, row * cell_h))

    out_path = figures_dir / f"{panel['id']}.png"
    canvas.save(str(out_path))
    print(f"Generated panel (PNG): {out_path}")


# ── Video figure generation ───────────────────────────────────────────────────

def _build_video_html_fragment(b64: str, fig_id: str) -> str:
    """
    Build a self-contained HTML document for a video figure.

    The "Camera View" button is injected at the paper level (analysis_report.html)
    by shortcodes.lua, so it is never inside this iframe and cannot be blocked by
    the video element's compositor layer.

    Parameters
    ----------
    b64: base64-encoded MP4 bytes (for the data URI)
    fig_id: figure identifier string
    """
    return (
        f'<!DOCTYPE html>\n'
        f'<html style="height:100%;margin:0;padding:0;">\n'
        f'<head><meta charset="utf-8">'
        f'<style>html,body{{margin:0;padding:0;overflow:hidden;height:100%;width:100%;}}</style>'
        f'</head>\n'
        f'<body>\n'
        f'<div style="position:relative;width:100%;height:100%;">\n'
        f'  <video src="data:video/mp4;base64,{b64}"\n'
        f'    controls loop autoplay muted playsinline\n'
        f'    style="width:100%;height:100%;border-radius:4px;display:block;object-fit:contain;">\n'
        f'  </video>\n'
        f'</div>\n'
        f'</body>\n'
        f'</html>'
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
    stride: int = 1,
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
        raise RuntimeError(f"Simulation at {src_path} has no time steps.")

    # Pass 1 — compute global scalar range across all timesteps
    print(f"{fig_id}: computing global range over {n_steps} frames …", file=sys.stderr)
    global_min = float("inf")
    global_max = float("-inf")
    step_indices = list(range(0, n_steps, stride))
    for idx in step_indices:
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
            f"Warning: field '{field}' not found — rendering geometry only.",
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
    print(f"{fig_id}: rendering {len(step_indices)} frames at {fps} fps (stride={stride}) …", file=sys.stderr)
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
        total_frames = len(step_indices)
        for i, idx in enumerate(step_indices):
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
            if (i + 1) % 10 == 0 or i == total_frames - 1:
                print(
                    f"{fig_id}: frame {i + 1}/{total_frames}",
                    file=sys.stderr,
                )
    finally:
        writer.close()
    print(f"Generated (MP4): {mp4_path}", file=sys.stderr)

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
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        pl.screenshot(str(frame_path))
        pl.close()
        print(f"Generated (frame PNG): {frame_path}", file=sys.stderr)

    # Generate interactive vtk.js preview served at /state/figures/<id>-preview.html
    # The paper page relay opens this as an overlay when "Camera View" is clicked.
    if preview_html_path is None:
        preview_html_path = video_html_path.parent / f"{fig_id}-preview.html"
    try:
        generate_html_figure(
            src_path, field, time_spec,
            preview_html_path,
            fig_id=fig_id,
            available_fields=[],
            camera_preview_only=True,
        )
    except Exception as exc:
        print(
            f"Warning: could not generate preview for {fig_id}: {exc}.",
            file=sys.stderr,
        )

    # Build self-contained HTML document with base64-encoded MP4 data URI
    b64 = base64.b64encode(mp4_path.read_bytes()).decode("ascii")
    video_html = _build_video_html_fragment(b64, fig_id)
    video_html_path.parent.mkdir(parents=True, exist_ok=True)
    video_html_path.write_text(video_html, encoding="utf-8")
    _maybe_sign_output_html(video_html_path)
    print(f"Generated (video HTML): {video_html_path}", file=sys.stderr)


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    if os.environ.get("QUARTO_NO_EXECUTE"):
        print("--no-execute mode: skipping figure generation.", file=sys.stderr)
        return

    strict_static_export = os.environ.get("FOURD_STRICT_STATIC_EXPORT") == "1"
    qmd_path = os.environ.get("QUARTO_DOCUMENT_PATH", "")
    # QUARTO_OUTPUT_FORMAT is not reliably set for project-level pre-render hooks.
    # We always generate both .html and .png so both HTML and PDF output work.
    output_format = os.environ.get("QUARTO_OUTPUT_FORMAT", "html")  # kept for logging only

    # QUARTO_DOCUMENT_PATH is not always set for project-level pre-render hooks.
    # Fall back to following includes from main.qmd (or analysis_report.qmd).
    if qmd_path and Path(qmd_path).exists():
        qmd_files = [Path(qmd_path)]
    else:
        project_dir = Path(os.environ.get("QUARTO_PROJECT_DIR", str(_project_root)))

        def collect_includes(qmd: Path, seen: set) -> list:
            if qmd in seen or not qmd.exists():
                return []
            seen.add(qmd)
            result = [qmd]
            for m in re.finditer(r'\{\{<\s*include\s+([^\s>]+)\s*>\}\}', qmd.read_text()):
                child = (qmd.parent / m.group(1)).resolve()
                result.extend(collect_includes(child, seen))
            return result

        for candidate in ["main.qmd", "analysis_report.qmd"]:
            root_qmd = project_dir / candidate
            if root_qmd.exists():
                qmd_files = collect_includes(root_qmd, set())
                break
        else:
            qmd_files = sorted(project_dir.glob("*.qmd"))

        if not qmd_files:
            print("No .qmd files found — skipping.", file=sys.stderr)
            return
        print(f"Scanning {len(qmd_files)} QMD file(s) in {project_dir}", file=sys.stderr)

    figures = []
    videos = []
    panels = []
    ts_raw = []
    graphs = []
    for qmd in qmd_files:
        text = qmd.read_text()
        figures.extend(parse_shortcodes(text))
        videos.extend(parse_video_shortcodes(text))
        panels.extend(parse_panel_shortcodes(text))
        ts_raw.extend(parse_timeseries_shortcodes(text))
        graphs.extend(parse_graph_shortcodes(text))

    if not any([figures, videos, panels, ts_raw, graphs]):
        print("No 4d-image, 4d-video, 4d-panel, 4d-timeseries, or 4d-graph shortcodes found.", file=sys.stderr)
        return

    figures_dir = _project_root / "state" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Load style templates once for all figures
    styles_yml_path = _project_root / "_4dpaper_styles.yml"
    styles_config = load_styles(styles_yml_path)
    styles_extra_deps = [styles_yml_path] if styles_yml_path.exists() else []
    qmd_extra_deps = [qmd for qmd in qmd_files if qmd.exists()]
    shortcut_extra_deps = [_shortcuts_yml_path] if _shortcuts_yml_path.exists() else []
    figure_extra_deps = styles_extra_deps + qmd_extra_deps + shortcut_extra_deps

    # Expand timeseries into optimized or panel-compatible dicts
    optimized_timeseries = []
    if ts_raw:
        from scripts.data_loader import SimulationData as _SimData  # noqa: PLC0415
    for ts in ts_raw:
        src = resolve_src_path(ts["src"])
        try:
            sim = _SimData(str(src)).load()
            n_steps = sim.n_steps
        except Exception as exc:
            print(f"ERROR loading simulation for timeseries '{ts['id']}': {exc}", file=sys.stderr)
            sys.exit(1)
        step_indices = _expand_timeseries_steps(ts, n_steps)

        # Check if mesh is identical across all timesteps
        if _check_same_mesh_timeseries(src, step_indices):
            print(f"Timeseries '{ts['id']}' has same mesh — using optimized compression", file=sys.stderr)
            optimized_timeseries.append({
                "id": ts["id"],
                "src": ts["src"],
                "src_path": src,
                "step_indices": step_indices,
                "field": ts["field"],
                "fields": ts.get("fields", ""),
                "caption": ts.get("caption", ""),
            })
        else:
            # Fallback: convert to panel
            print(f"Timeseries '{ts['id']}' has changing mesh — using panel layout", file=sys.stderr)
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

    # Generate optimized timeseries HTML (compressed mesh, same across timesteps)
    # Falls back to panel approach if optimization fails
    for ts in optimized_timeseries:
        ts_id = ts["id"]
        output_path = figures_dir / f"{ts_id}.html"

        # Cache check
        if is_cache_valid(output_path, ts["src_path"], extra_deps=figure_extra_deps):
            print(f"{ts_id}.html is up to date — skipping.", file=sys.stderr)
            continue

        try:
            style = resolve_style(styles_config, "", ts["field"])
            _generate_optimized_timeseries_html(
                ts_id=ts_id,
                src=ts["src_path"],
                step_indices=ts["step_indices"],
                field=ts["field"],
                fields_attr=ts["fields"],
                figures_dir=figures_dir,
                style=style,
                caption=ts["caption"],
            )
        except Exception as exc:
            print(f"WARNING: optimized timeseries {ts_id} failed ({exc}), falling back to panel approach", file=sys.stderr)
            # Fallback: convert to panel and re-add to panels list
            ts_panel = {
                "id": ts_id,
                "subfigures": [
                    {
                        "src":    ts["src"],
                        "id":     f"{ts_id}-{i}",
                        "field":  ts["field"],
                        "time":   str(idx),
                        "fields": "",
                    }
                    for i, idx in enumerate(ts["step_indices"])
                ],
                "layout": f"{len(ts['step_indices'])}x1",
                "caption": ts.get("caption", ""),
            }
            panels.append(ts_panel)

    for fig in figures:
        fig_id = fig["id"]
        src = resolve_src_path(fig["src"])
        field = fig["field"]
        time_spec = fig.get("time", "mid")
        style = resolve_style(styles_config, fig["style"], field)

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
        field, time_spec = _load_saved_field_state(fig_id, field, time_spec)

        # Always generate both .html (for web) and .png (for PDF).
        # QUARTO_OUTPUT_FORMAT is not reliably set for project pre-render hooks,
        # so we keep both formats up to date on every render pass.
        out_html = figures_dir / f"{fig_id}.html"
        # Also invalidate HTML cache if this script itself changed (e.g. new camera snippet).
        script_newer = (
            out_html.exists()
            and _here.stat().st_mtime > out_html.stat().st_mtime
        )
        if not script_newer and is_cache_valid(out_html, src, field_path=field_state_path, extra_deps=figure_extra_deps):
            print(f"{fig_id}.html is up to date — skipping.", file=sys.stderr)
        else:
            print(f"Generating {fig_id}.html …", file=sys.stderr)
            try:
                generate_html_figure(
                    src, field, time_spec, out_html,
                    fig_id=fig_id, available_fields=available_fields,
                    background=style["background"],
                    axis_color=style["axis_color"],
                    cmap=style["cmap"],
                    decimate=fig.get("decimate", "auto"),
                    stride=int(fig.get("stride", "1")),
                )
            except Exception as exc:
                print(f"ERROR generating {fig_id}.html: {exc}", file=sys.stderr)
                sys.exit(1)

        out_png = figures_dir / f"{fig_id}.png"
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"
        # Always report camera status so the user can verify what's used in PDF.
        if camera_path.exists():
            try:
                cam = json.loads(camera_path.read_text())
                print(
                    f"Camera for {fig_id}: position={cam.get('position')}  "
                    f"(from state/camera_{fig_id}.json — rotate the 3D figure in the "
                    f"HTML preview to update)"
                )
            except Exception:
                print(f"Camera for {fig_id}: file exists but is invalid — will use isometric view")
        else:
            print(
                f"Camera for {fig_id}: NOT SET — isometric view will be used. "
                f"Rotate the figure in the HTML preview to save a camera position."
            )
        # Always regenerate PNG when a camera file exists...
        png_fresh = is_cache_valid(out_png, src, camera_path=camera_path, field_path=field_state_path, extra_deps=figure_extra_deps)
        if png_fresh:
            print(f"{fig_id}.png is up to date — skipping.")
        else:
            print(f"Generating {fig_id}.png …")
            try:
                generate_png_figure(
                    src, field, time_spec, out_png, fig_id=fig_id,
                    background=style["background"],
                    axis_color=style["axis_color"],
                    cmap=style["cmap"],
                    decimate=fig.get("decimate", "auto"),
                )
            except Exception as exc:
                if strict_static_export:
                    print(f"ERROR: could not generate {fig_id}.png: {exc}")
                    print("  Static figure generation is required for PDF/paperview export.")
                    sys.exit(1)
                print(f"WARNING: could not generate {fig_id}.png: {exc}")
                print("  PNG is needed for PDF export only — HTML render continues.")

    # ── Video shortcode processing ─────────────────────────────────────────────
    for vid in videos:
        fig_id = vid["id"]
        src = resolve_src_path(vid["src"])
        field = vid["field"]
        time_spec = vid.get("time", "mid")
        fps = int(vid.get("fps", "10"))
        stride = int(vid.get("stride", "1"))

        mp4_path = figures_dir / f"{fig_id}-video.mp4"
        frame_path = figures_dir / f"{fig_id}-frame.png"
        video_html_path = figures_dir / f"{fig_id}-video.html"
        preview_html_path = figures_dir / f"{fig_id}-preview.html"
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"

        mp4_valid = is_cache_valid(mp4_path, src, camera_path=camera_path, extra_deps=qmd_extra_deps + shortcut_extra_deps)
        frame_valid = is_cache_valid(frame_path, src, camera_path=camera_path, extra_deps=qmd_extra_deps + shortcut_extra_deps)
        # Also invalidate video HTML when this script changes (contains injected content)
        script_newer_vid = (
            video_html_path.exists()
            and _here.stat().st_mtime > video_html_path.stat().st_mtime
        )
        html_valid = (
            not script_newer_vid
            and is_cache_valid(video_html_path, src, camera_path=camera_path, extra_deps=qmd_extra_deps + shortcut_extra_deps)
        )

        if mp4_valid and frame_valid and html_valid:
            print(f"{fig_id} video outputs are up to date — skipping.", file=sys.stderr)
            continue

        print(f"Generating video for {fig_id} …", file=sys.stderr)
        try:
            generate_video_figure(
                src, field, fps, time_spec,
                mp4_path, frame_path, video_html_path,
                fig_id=fig_id,
                preview_html_path=preview_html_path,
                stride=stride,
            )
        except Exception as exc:
            print(f"ERROR generating video {fig_id}: {exc}", file=sys.stderr)
            sys.exit(1)

    # ── Panel shortcode processing ─────────────────────────────────────────────
    for panel in panels:
        panel_id = panel["id"]
        camera_mode = panel.get("camera_mode", "independent")
        out_html = figures_dir / f"{panel_id}.html"
        out_png  = figures_dir / f"{panel_id}.png"

        # Determine max mtime of all sub-figure source files and camera deps
        sub_mtimes = []
        for sub in panel["subfigures"]:
            src = resolve_src_path(sub["src"])
            if src.exists():
                sub_mtimes.append(src.stat().st_mtime)
            field_state = _project_root / "state" / f"field_{sub['id']}.json"
            if field_state.exists():
                sub_mtimes.append(field_state.stat().st_mtime)
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

        if out_html.exists() and out_html.stat().st_mtime >= max_dep_mtime:
            print(f"{panel_id}.html is up to date — skipping.", file=sys.stderr)
        else:
            print(f"Generating panel {panel_id}.html …", file=sys.stderr)
            try:
                generate_panel_html(panel, figures_dir)
            except Exception as exc:
                print(f"ERROR generating panel {panel_id}.html: {exc}", file=sys.stderr)
                sys.exit(1)

        if out_png.exists() and out_png.stat().st_mtime >= max_dep_mtime:
            print(f"{panel_id}.png is up to date — skipping.")
        else:
            print(f"Generating panel {panel_id}.png …")
            try:
                generate_panel_png(panel, figures_dir)
            except Exception as exc:
                print(f"ERROR generating panel {panel_id}.png: {exc}")
                sys.exit(1)

    for graph in graphs:
        fig_id = graph["id"]
        src = resolve_src_path(graph["src"])

        out_html = figures_dir / f"{fig_id}.html"
        out_png = figures_dir / f"{fig_id}.png"
        
        script_newer = out_html.exists() and _here.stat().st_mtime > out_html.stat().st_mtime
        cache_ok = (
            not script_newer
            and is_cache_valid(out_html, src, extra_deps=qmd_extra_deps + shortcut_extra_deps)
            and is_cache_valid(out_png, src, extra_deps=qmd_extra_deps + shortcut_extra_deps)
        )
        
        if cache_ok:
            print(f"{fig_id} Graph outputs are up to date -- skipping.", file=sys.stderr)
            continue
            
        print(f"Generating Graph figure for {fig_id} ({src}) ...", file=sys.stderr)
        try:
            import plotly.io as pio
            import plotly.graph_objects as go

            with open(src, "r") as f:
                fig_dict = json.load(f)

            # Apply RDP simplification to every trace that carries (x, y) arrays.
            for trace in fig_dict.get("data", []):
                xs = trace.get("x")
                ys = trace.get("y")
                if (isinstance(xs, list) and isinstance(ys, list)
                        and len(xs) == len(ys) and len(xs) > 2):
                    n_before = len(xs)
                    xs_s, ys_s = _rdp_simplify_xy(xs, ys)
                    n_after = len(xs_s)
                    if n_after < n_before:
                        trace["x"] = xs_s
                        trace["y"] = ys_s
                        pct = 100.0 * (1.0 - n_after / n_before)
                        tname = trace.get("name", "")
                        print(
                            f"{fig_id} RDP{f' ({tname})' if tname else ''}: "
                            f"{n_before:,} → {n_after:,} points ({pct:.1f}% reduction)",
                            file=sys.stderr,
                        )

            fig = go.Figure(fig_dict)
            
            # Export PNG for static PDF builds. Plotly auto-selects Kaleido when installed.
            pio.write_image(fig, out_png, format="png", scale=2)
            
            # Re-theme the figure background so it matches the surrounding page neatly
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

            # Export standalone HTML for interactive web
            html_content = pio.to_html(fig, full_html=True, include_plotlyjs="cdn", config={'displayModeBar': False})
            
            # Inject 4dpaper HUD controls (Lock button, etc) so it acts like natively generated viewer
            inj_html = _controls_strip_snippet(fig_id, show_orientation=False)
            if '</body>' in html_content:
                html_content = html_content.replace('</body>', inj_html + '\n</body>', 1)
            else:
                html_content += inj_html
                
            out_html.write_text(html_content, encoding="utf-8")
            _maybe_sign_output_html(out_html)
        except Exception as exc:
            print(f"ERROR generating Graph figure {fig_id}: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
