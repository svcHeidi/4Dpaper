#!/usr/bin/env python3
"""
4DPaper pre-render hook — run by Quarto before rendering.

Scans the .qmd for {{< 4d-image >}} shortcodes and generates
figure files in state/figures/ (HTML for web, PNG for PDF).

Quarto calls this script before rendering. It reads QUARTO_DOCUMENT_PATH
and QUARTO_OUTPUT_FORMAT from the environment.
"""
from __future__ import annotations

import array as _array
import base64 as _b64
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── Environment & Paths ───────────────────────────────────────────────────────
_here = Path(__file__).resolve()
_ext_dir = _here.parent
_assets_dir = _ext_dir / "assets"
_project_root = _ext_dir.parent.parent if _ext_dir.name == "4dpaper" else _ext_dir.parent
_venv_python = _project_root / ".venv" / "bin" / "python"

# Figures and state directory (relative to project root usually, or CWD)
# In Quarto, CWD is the project root during pre-render.
STATE_DIR = Path("state")
FIGURES_DIR = STATE_DIR / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

_under_pytest = "pytest" in sys.modules or any("pytest" in a for a in sys.argv)
if (
    _venv_python.exists()
    and not _under_pytest
    and sys.prefix != str(_project_root / ".venv")
):
    os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

# Add project root to path for scripts/
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

def _log(msg: str, level: str = "INFO") -> None:
    """Standardized logging with prefix and stderr routing."""
    print(f"[4dpaper] {level}: {msg}", file=sys.stderr)

def find_pvpython() -> Path | None:
    """
    Search for pvpython in:
    1. FOURD_PVPYTHON env var
    2. System PATH
    3. Standard installation paths
    """
    # 1. Env var
    env_path = os.environ.get("FOURD_PVPYTHON")
    if env_path:
        p = Path(env_path)
        if p.exists(): return p

    # 2. PATH
    sys_path = shutil.which("pvpython")
    if sys_path: return Path(sys_path)

    # 3. Standard paths (Mac/Linux)
    standards = [
        Path("/Applications/ParaView-6.0.1.app/Contents/bin/pvpython"),
        Path("/Applications/ParaView-5.11.0.app/Contents/bin/pvpython"),
        Path("/usr/local/bin/pvpython"),
        Path("/usr/bin/pvpython"),
    ]
    for p in standards:
        if p.exists(): return p

    return None

def get_asset(name: str) -> str:
    """Read an asset file from the extensions/assets directory."""
    path = _assets_dir / name
    if not path.exists():
        _log(f"Asset '{name}' not found at {path}", level="WARN")
        return ""
    return path.read_text(encoding="utf-8")


def _parse_general_shortcodes(text: str, tag: str, defaults: dict[str, str]) -> list[dict]:
    """Generic shortcode parser for {{< tag key="value" ... >}}."""
    stripped = re.sub(r'(`{1,3}).*?\1', '', text, flags=re.DOTALL)
    pattern = rf'\{{\{{<\s*{tag}\s+(.*?)\s*>\}}\}}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs = defaults.copy()
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        
        if "id" not in kwargs:
            _log(f"{tag} shortcode missing 'id' — skipping.", level="WARN")
            continue
        if tag in ["4d-image", "4d-video", "4d-timeseries", "4d-pvsm", "4d-graph"] and "src" not in kwargs:
            _log(f"{tag} shortcode missing 'src' — skipping.", level="WARN")
            continue
            
        results.append(kwargs)
    return results

def parse_timeseries_shortcodes(text: str) -> list[dict]:
    raw_ts = _parse_general_shortcodes(text, "4d-timeseries", {
        "height": "400px", "caption": "", "field": "", "steps": "4", "times": ""
    })
    results = []
    for ts in raw_ts:
        results.append({
            "id": ts["id"], "src": ts["src"], "height": ts["height"],
            "caption": ts["caption"], "camera_mode": "sync", "timeseries": True,
            "field": ts["field"], "steps": ts["steps"], "times": ts["times"],
            "subfigures": []
        })
    return results

def parse_video_shortcodes(text: str) -> list[dict]:
    return _parse_general_shortcodes(text, "4d-video", {
        "fps": "10", 
        "time": "mid", 
        "field": ""
    })

def parse_shortcodes(text: str) -> list[dict]:
    return _parse_general_shortcodes(text, "4d-image", {
        "time": "mid",
        "field": "",
        "fields": "",
        "style": ""
    })

def parse_panel_shortcodes(text: str) -> list[dict]:
    raw_panels = _parse_general_shortcodes(text, "4d-panel", {
        "layout": "1x1", "height": "800px", "caption": "", "camera": "independent"
    })
    
    results = []
    for p in raw_panels:
        subfigures = []
        n = 1
        while f"src{n}" in p:
            subfigures.append({
                "src":    p[f"src{n}"],
                "id":     p.get(f"id{n}", f"panel-sub-{n}"),
                "field":  p.get(f"field{n}", ""),
                "time":   p.get(f"time{n}", "mid"),
                "fields": p.get(f"fields{n}", ""),
            })
            n += 1
            
        if not subfigures:
            _log(f"4d-panel '{p['id']}' has no sub-figures — skipping.", level="WARN")
            continue
            
        results.append({
            "id":          p["id"],
            "layout":      p["layout"],
            "height":      p["height"],
            "caption":     p["caption"],
            "camera_mode": p["camera"],
            "subfigures":  subfigures,
        })
    return results

def _expand_timeseries_steps(ts: dict, n_steps: int) -> list[int]:
    """Expand steps/times string to list of integer step indices."""
    if ts["times"]:
        result = []
        for tok in ts["times"].split(","):
            tok = tok.strip()
            if tok == "first": result.append(0)
            elif tok == "last": result.append(max(0, n_steps - 1))
            else:
                try: result.append(max(0, min(int(tok), n_steps - 1)))
                except ValueError: pass
        if result: return result

    if n_steps <= 1:
        _log(f"Timeseries '{ts['id']}' source has only {n_steps} step(s) — generating single frame.", level="WARN")
        return [0]
    N = max(2, int(ts.get("steps", "4")))
    return [round(i * (n_steps - 1) / (N - 1)) for i in range(N)]


def check_paraview_version(min_ver: str = "5.10.0", pvpython_path: Path | None = None) -> bool:
    """Check if pvpython meets the minimum version requirement."""
    import subprocess
    pv_exe = pvpython_path or find_pvpython()
    if not pv_exe:
        _log("ParaView (pvpython) not found. Required for PVSM rendering.", level="ERROR")
        return False
    try:
        out = subprocess.check_output([str(pv_exe), "--version"], stderr=subprocess.STDOUT, text=True)
        m = re.search(r"version\s+([\d\.]+)", out)
        if not m:
            _log(f"Could not parse ParaView version from: {out.strip()}", level="WARN")
            return False
        
        ver = m.group(1)
        v_tup = lambda v: tuple(map(int, v.split(".")))
        if v_tup(ver) < v_tup(min_ver):
            _log(f"ParaView version {ver} is < required {min_ver}", level="ERROR")
            return False
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        _log(f"ParaView version check failed: {exc}", level="ERROR")
        return False

# -- PVSM parsing ---------------------------------------------------------------

def parse_pvsm_shortcodes(text: str) -> list[dict]:
    return _parse_general_shortcodes(text, "4d-pvsm", {
        "data": "",
        "time": "",
        "caption": ""
    })

def parse_graph_shortcodes(text: str) -> list[dict]:
    return _parse_general_shortcodes(text, "4d-graph", {
        "caption": ""
    })


def parse_pvsm_color_info(pvsm_path: Path) -> dict:
    """
    Extract color/scalar info from a ParaView state (.pvsm) XML file.
    Uses manual XML parsing (robust against complex pipelines).
    """
    import xml.etree.ElementTree as ET
    from matplotlib.colors import LinearSegmentedColormap

    _PRESET_MAP = {
        "Cool to Warm":               "coolwarm",
        "Cool to Warm (Extended)":    "coolwarm",
        "Viridis (matplotlib)":       "viridis",
        "Plasma (matplotlib)":        "plasma",
        "Inferno (matplotlib)":       "inferno",
        "Magma (matplotlib)":         "magma",
        "Rainbow Desaturated":        "rainbow",
        "Blue to Red Rainbow":        "jet",
        "erdc_iceFire_H":             "coolwarm",
    }

    _FALLBACK = {
        "scalar_name": "",
        "field_association": "point",
        "vmin": 0.0,
        "vmax": 1.0,
        "cmap": "coolwarm",
    }

    if not pvsm_path.exists():
        return _FALLBACK.copy()

    try:
        tree = ET.parse(str(pvsm_path))
        root = tree.getroot()
        sms = root.find("ServerManagerState")
        if sms is None:
            return _FALLBACK.copy()

        # 1. Find the RenderView to see what's actually visible
        render_view = sms.find("Proxy[@group='views'][@type='RenderView']")
        visible_rep_ids = []
        if render_view is not None:
            reps_prop = render_view.find("Property[@name='Representations']")
            if reps_prop is not None:
                visible_rep_ids = [p.get("value") for p in reps_prop.findall("Proxy")]

        # 2. Find the leaf representation (the one whose Visibility is 1 or is in the view)
        # We pick the last visible representation in the XML as our 'terminal' source heuristic.
        leaf_rep_proxy = None
        for proxy in sms.findall("Proxy[@group='representations']"):
            proxy_id = proxy.get("id")
            # If we identified visible reps from the view, filter by them
            if visible_rep_ids and proxy_id not in visible_rep_ids:
                continue
            
            # Check for ColorArrayName property - if it's not coloring by something, it's likely a glyph/outline
            color_prop = proxy.find("Property[@name='ColorArrayName']")
            if color_prop is not None:
                leaf_rep_proxy = proxy

        if leaf_rep_proxy is None:
            return _FALLBACK.copy()

        assoc_val = "1"
        scalar_name = ""
        color_prop = leaf_rep_proxy.find("Property[@name='ColorArrayName']")
        if color_prop is not None:
            elems = color_prop.findall("Element")
            if len(elems) >= 5:
                assoc_val = elems[3].get("value", "1")
                scalar_name = elems[4].get("value", "")

        lut_id = ""
        lut_prop = leaf_rep_proxy.find("Property[@name='LookupTable']")
        if lut_prop is not None:
            lut_proxy_elem = lut_prop.find("Proxy")
            if lut_proxy_elem is not None:
                lut_id = lut_proxy_elem.get("value", "")

        vmin, vmax = 0.0, 1.0
        cmap = "coolwarm"

        if lut_id:
            lut_proxy = sms.find(f"Proxy[@id='{lut_id}']")
            if lut_proxy is not None:
                rgb_prop = lut_proxy.find("Property[@name='RGBPoints']")
                if rgb_prop is not None:
                    vals = [float(e.get("value", 0)) for e in rgb_prop.findall("Element")]
                    if len(vals) >= 8:
                        groups = [vals[i:i+4] for i in range(0, len(vals), 4)]
                        vmin, vmax = groups[0][0], groups[-1][0]
                        
                        preset_name = ""
                        preset_prop = lut_proxy.find("Property[@name='NameOfLastPresetApplied']")
                        if preset_prop is not None:
                            elem = preset_prop.find("Element")
                            if elem is not None: preset_name = elem.get("value", "")

                        if preset_name in _PRESET_MAP:
                            cmap = _PRESET_MAP[preset_name]
                        else:
                            span = max(1e-10, vmax - vmin)
                            norm_colors = [((g[0]-vmin)/span, (g[1],g[2],g[3])) for g in groups]
                            cmap = LinearSegmentedColormap.from_list("pvsm", norm_colors)

        return {
            "scalar_name": scalar_name,
            "field_association": "point" if assoc_val == "1" else "cell",
            "vmin": vmin, "vmax": vmax, "cmap": cmap,
        }
    except Exception as exc:
        print(f"[4dpaper] Warning: PVSM parsing failed for {pvsm_path.name} ({exc})", file=sys.stderr)
        return _FALLBACK.copy()

    except Exception as exc:
        print(f"[4dpaper] WARNING: PVSM color parsing failed ({exc}); using defaults.", file=sys.stderr)
        return _FALLBACK.copy()


# ── Cache helpers ─────────────────────────────────────────────────────────────

def is_cache_valid(
    fig_path: Path,
    src_path: Path,
    camera_path: Path | None = None,
    field_path: Path | None = None,
    extra_deps: list[Path] | None = None,
) -> bool:
    """
    Returns True if fig_path exists and is newer than all dependencies.
    Dependencies include: source, camera, fields, additional deps, and the extension itself.
    """
    if not fig_path.exists(): return False
    
    deps = [src_path]
    if camera_path and camera_path.exists(): deps.append(camera_path)
    if field_path and field_path.exists(): deps.append(field_path)
    if extra_deps: deps.extend(extra_deps)
    
    # Global extension dependencies: the script itself and all assets.
    deps.append(_here)
    if _assets_dir.exists():
        for asset in _assets_dir.iterdir():
            if asset.is_file(): deps.append(asset)
    
    fig_mtime = fig_path.stat().st_mtime
    for d in deps:
        if d.exists() and d.stat().st_mtime > fig_mtime:
            return False
    return True


# -- Style template loading and resolution ------------------------------------

def load_styles(path: Path) -> dict:
    """
    Load _4dpaper_styles.yml. Returns {} on missing or malformed file.
    Never raises — warnings go to stderr.
    """
    if not path.exists():
        return {}
    try:
        import yaml
        with path.open() as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            print(f"[4dpaper] WARNING: {path} is not a YAML mapping — ignoring styles.", file=sys.stderr)
            return {}
        return data
    except Exception as exc:
        print(f"[4dpaper] WARNING: could not load {path}: {exc} — ignoring styles.", file=sys.stderr)
        return {}


def resolve_style(styles_config: dict, style_name: str, field_name: str) -> dict:
    """
    Resolve {background, axis_color, cmap} from styles config.

    Pure function — no I/O. Safe to call with empty styles_config.
    'transparent' background is normalised to 'white' (PyVista limitation).
    """
    _HARD = {"background": "white", "axis_color": "black", "cmap": "coolwarm"}

    defaults = styles_config.get("defaults", {}) if styles_config else {}
    styles   = styles_config.get("styles",   {}) if styles_config else {}

    # Start from hard defaults, override with file-level defaults
    resolved = {
        "background": defaults.get("background", _HARD["background"]),
        "axis_color": defaults.get("axis_color", _HARD["axis_color"]),
        "cmap":       defaults.get("cmap",       _HARD["cmap"]),
    }

    # Apply named style overrides (skip silently if style_name is "")
    if style_name:
        if style_name not in styles:
            print(
                f"[4dpaper] WARNING: style '{style_name}' not found in styles config — using defaults.",
                file=sys.stderr,
            )
        else:
            tmpl = styles[style_name]
            if "background"  in tmpl: resolved["background"]  = tmpl["background"]
            if "axis_color"  in tmpl: resolved["axis_color"]  = tmpl["axis_color"]
            if "cmap"        in tmpl: resolved["cmap"]        = tmpl["cmap"]
            # Per-field cmap override
            field_cmaps = tmpl.get("fields", {})
            if field_name and field_name in field_cmaps:
                resolved["cmap"] = field_cmaps[field_name]

    # Normalise 'transparent' → 'white' (PyVista does not support transparent backgrounds)
    if resolved["background"] == "transparent":
        resolved["background"] = "white"

    return resolved


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


# ── Unified controls strip snippet ────────────────────────────────────────────

def _controls_strip_snippet(
    fig_id: str,
    show_lock_btn: bool = True,
    show_orientation: bool = True,
    fields_to_embed: list[str] | None = None,
    active_field: str = "",
    field_data: dict | None = None,
    field_ranges: dict | None = None,
    time_labels: list[str] | None = None,
    time_data: list[str] | None = None,
    time_global_range: list[float] | None = None,
    time_idx: int = 0,
    time_field: str = "",
) -> str:
    """
    Return a combined HTML+JS block that adds a right-edge icon strip to a
    vtk.js figure, with popup panels for camera lock, orientation axes/presets,
    field switching, and time scrubbing.

    The figure surface has zero UI overlay — all controls live in the strip.
    Exactly one panel is open at a time; clicking the active icon closes it.

    Replaces _camera_sync_snippet, _field_sync_snippet, _time_sync_snippet,
    and _orientation_snippet.
    """
    fig_id_js = json.dumps(fig_id).replace("</", "<\\/")
    fig_id_safe = fig_id.replace("</", "<\\/").replace('"', '').replace("-", "_")

    has_fields = bool(fields_to_embed and len(fields_to_embed) > 1)
    has_time = bool(time_labels and len(time_labels) > 1 and time_data)
    n_time = len(time_data) if time_data else 0

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

    # ── UI Presentation Layer ────────────────────────────────────────────────
    # Load the pure-HTML skeleton (placeholders-free)
    html_skeleton = get_asset("viewer_controls.html") or "<!-- viewer_controls.html missing -->"
    
    # Load the premium styling
    premium_css = get_asset("viewer.css") or ""
    css_block = f'<style>\n{premium_css}\n</style>\n'
    
    # Prepare the Data Contract
    config = {
        "figureId": fig_id,
        "activeField": active_field,
        "availableFields": fields_to_embed or [],
        "fieldData": field_data or {},
        "fieldRanges": field_ranges or {},
        "timeIdx": time_idx,
        "timeLabels": time_labels or [],
        "timeData": time_data or [],
        "timeGlobalRange": time_global_range or [0, 1],
        "showLockBtn": show_lock_btn,
        "showOrientation": show_orientation
    }
    config_json = json.dumps(config).replace("</", "<\\/")
    
    # Load the logic asset
    logic_js = get_asset("viewer_logic.js") or "console.error('viewer_logic.js not found');"
    
    # Combined output
    # Note: we can still append the legacy strip_btns if they were generated,
    # but the new logic expects them to be part of the contract or standard IDs.
    html_block = html_skeleton
    js_block = f'<script>\nwindow.FOURD_CONFIG = {config_json};\n{logic_js}\n</script>\n'
    
    return css_block + html_block + js_block


# ── Figure generation (Task 3) ────────────────────────────────────────────────

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
            f"[4dpaper] Warning: field '{field}' not found — rendering geometry only.",
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
    print(f"[4dpaper] Generated (PNG): {output_path}")


def generate_html_figure(
    src_path: Path,
    field: str,
    time_spec: str,
    output_path: Path,
    fig_id: str | None = None,
    available_fields: list[str] | None = None,
    camera_preview_only: bool = False,
    background: str = "white",
    axis_color: str = "black",
    cmap: str = "coolwarm",
    show_colorbar: bool = True,
    show_lock_btn: bool = True,
    show_orientation: bool = True,
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
            f"[4dpaper] Warning: field '{field}' not found in mesh — rendering geometry only.",
            file=sys.stderr,
        )

    # Apply camera — same logic as generate_png_figure so HTML and PDF start from
    # the same viewpoint.
    camera_path = (_project_root / "state" / f"camera_{fig_id}.json" if fig_id else None)
    apply_camera_state(pl, fig_id or "unnamed", camera_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    data_dir = output_path.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    pl.export_html(str(output_path))
    pl.close()

    # ── Prepare field data blobs for live switching ───────────────────────────
    # For each switchable field (other than the one already rendered), extract
    # the scalar array as Float32, cell→point interpolated to match what
    # trame serialises for the active field.
    # New: Save as raw binary files (.bin) instead of base64 strings.
    fields_to_embed = list(available_fields) if available_fields else [field]
    field_data_urls: dict[str, str] = {}
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
        
        # Save as binary file
        bin_name = f"{fig_id or 'fig'}_f_{f}.bin"
        (data_dir / bin_name).write_bytes(arr_f32.tobytes())
        
        field_data_urls[f] = f"data/{bin_name}"
        field_ranges[f] = [float(arr_f32.min()), float(arr_f32.max())]

    # ── Prepare time step data blobs (one per step, active field only) ────────
    # Each entry is a URL to a binary Float32Array of the scalar values at that step.
    # Empty string is used as a placeholder when a step's data is unavailable.
    time_data_urls: list[str] = []
    time_labels: list[str] = []
    time_global_min = float("inf")
    time_global_max = float("-inf")

    if sim.n_steps > 1 and field:
        print(
            f"[4dpaper] {fig_id or 'fig'}: generating binary data for {sim.n_steps} timesteps …",
            file=sys.stderr,
        )
        for t_idx in range(sim.n_steps):
            t_mesh = sim.get_mesh(t_idx)
            if t_mesh is None:
                time_data_urls.append("")
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
                
                # Save as binary file
                bin_name = f"{fig_id or 'fig'}_t_{t_idx}.bin"
                (data_dir / bin_name).write_bytes(arr_f32.tobytes())
                
                time_data_urls.append(f"data/{bin_name}")
                time_global_min = min(time_global_min, float(arr_f32.min()))
                time_global_max = max(time_global_max, float(arr_f32.max()))
            else:
                time_data_urls.append("")
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
                    field_data=field_data_urls,
                    field_ranges=field_ranges,
                    time_labels=time_labels,
                    time_data=time_data_urls,
                    time_global_range=time_global_range,
                    time_idx=idx,
                    time_field=field,
                ) + "\n</body>"
            html = html.replace("</body>", inj_html, 1)
    output_path.write_text(html)

    print(f"[4dpaper] Generated: {output_path}", file=sys.stderr)


def generate_html_from_vtu(
    vtu_path: Path,
    out_html: Path,
    fig_id: str,
    scalar_name: str,
    clim: list[float],
    cmap,
    field_association: str,
    preview: bool = False,
) -> None:
    """
    Export a PyVista HTML figure from a .vtu geometry file.

    Uses off_screen=False so that export_html() initialises the WebGL exporter
    correctly -- same pattern as generate_html_figure().
    """
    import pyvista as pv

    mesh = pv.read(str(vtu_path))

    pl = pv.Plotter(off_screen=False)
    pl.background_color = "#1a1a2e"

    add_kwargs: dict = dict(cmap=cmap, preference=field_association)
    if scalar_name and scalar_name in {**mesh.point_data, **mesh.cell_data}:
        add_kwargs["scalars"] = scalar_name
        add_kwargs["clim"] = clim

    pl.add_mesh(mesh, **add_kwargs)

    if not preview:
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"
        if camera_path.exists():
            try:
                cam = json.loads(camera_path.read_text())
                _apply_camera_from_dict(pl, fig_id, cam)
            except Exception as exc:
                print(f"[4dpaper] WARNING: could not apply camera for {fig_id}: {exc}", file=sys.stderr)
        else:
            pl.isometric_view()
    else:
        pl.isometric_view()

    out_html.parent.mkdir(parents=True, exist_ok=True)
    pl.export_html(str(out_html))
    pl.close()


def generate_pvsm_figure(
    pvsm_path: Path,
    fig_id: str,
    figures_dir: Path,
    data_path: Path | None = None,
    time_spec: str | None = None,
    pvpython_path: Path | None = None,
) -> None:
    """
    Render a .pvsm state file to .vtu geometry and .png screenshot using pvpython.
    Injects 4dpaper HUD controls into the resulting .html file.
    """
    import subprocess

    pv_exe = pvpython_path or find_pvpython()
    if not pv_exe:
        raise RuntimeError(f"[4dpaper] ERROR: ParaView (pvpython) not found. Required for PVSM rendering.")

    # Validate version before proceeding
    if not check_paraview_version("6.0.1", pvpython_path=pv_exe):
         _log(f"ParaView version check failed for {fig_id}. Proceeding with caution.", level="WARN")

    pvsm_render_script = _ext_dir / "pvsm_render.py"
    out_vtu     = figures_dir / f"{fig_id}-pipeline.vtu"
    out_png     = figures_dir / f"{fig_id}.png"
    out_html    = figures_dir / f"{fig_id}.html"
    out_preview = figures_dir / f"{fig_id}-preview.html"
    camera_path = _project_root / "state" / f"camera_{fig_id}.json"

    # -- Step 1: pvpython subprocess -------------------------------------------
    color_info = parse_pvsm_color_info(pvsm_path)

    cmd = [
        str(pv_exe), str(pvsm_render_script),
        "--pvsm",    str(pvsm_path),
        "--out-vtu", str(out_vtu),
        "--out-png", str(out_png),
    ]
    if data_path:
        cmd += ["--data", str(data_path)]
    if time_spec:
        cmd += ["--time", str(time_spec)]
    if camera_path.exists():
        cmd += ["--camera", str(camera_path)]
    if not time_spec and color_info.get("scalar_name"):
        cmd += ["--all-times", "--scalar", color_info["scalar_name"]]

    _log(f"Running pvpython for {fig_id} ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout: _log(result.stdout.strip())
    if result.stderr: _log(result.stderr.strip(), level="DEBUG")
    if result.returncode != 0:
        raise RuntimeError(f"pvpython failed for {fig_id} (exit {result.returncode}).")

    if not out_vtu.exists():
        raise RuntimeError(f"pvpython did not produce {out_vtu}")

    # -- Step 2: PyVista HTML export -------------------------------------------

    _log(f"Generating {fig_id}.html from VTU ...")
    generate_html_from_vtu(
        vtu_path=out_vtu,
        out_html=out_html,
        fig_id=fig_id,
        scalar_name=color_info["scalar_name"],
        clim=[color_info["vmin"], color_info["vmax"]],
        cmap=color_info["cmap"],
        field_association=color_info["field_association"],
        preview=False,
    )

    _log(f"Generating {fig_id}-preview.html ...")
    generate_html_from_vtu(
        vtu_path=out_vtu,
        out_html=out_preview,
        fig_id=fig_id,
        scalar_name=color_info["scalar_name"],
        clim=[color_info["vmin"], color_info["vmax"]],
        cmap=color_info["cmap"],
        field_association=color_info["field_association"],
        preview=True,
    )

    # -- Step 3: Build time data and inject controls ----------------------------
    scalar_name = color_info.get("scalar_name", "") or ""
    time_labels: list[str] | None = None
    time_data_b64: list[str] | None = None
    time_global_range: list[float] | None = None

    # Only attempt time embedding when no specific time step was requested
    # and the PVSM has an active scalar field.
    if not time_spec and scalar_name:
        times_json = figures_dir / f"{fig_id}-times.json"
        if times_json.exists():
            try:
                time_labels = json.loads(times_json.read_text(encoding="utf-8"))
                arrays = []
                for i in range(len(time_labels)):
                    bin_path = figures_dir / f"{fig_id}-scalars-t{i}.bin"
                    raw = bin_path.read_bytes()
                    arr = _array.array("f")
                    arr.frombytes(raw)
                    arrays.append(arr)

                # Topology guard: all frame arrays must have the same length
                ref_len = len(arrays[0]) if arrays else 0
                if any(len(a) != ref_len for a in arrays):
                    print(
                        f"[4dpaper] WARNING: {fig_id} — mesh topology changes between "
                        "time steps; time scrubber disabled.",
                        file=sys.stderr,
                    )
                    time_labels = None
                    time_data_b64 = None
                else:
                    time_data_b64 = [
                        _b64.b64encode(a.tobytes()).decode("ascii") for a in arrays
                    ]
                    time_global_range = [
                        float(min(min(a) for a in arrays)),
                        float(max(max(a) for a in arrays)),
                    ]
            except (OSError, ValueError) as exc:
                print(
                    f"[4dpaper] WARNING: {fig_id} — could not load time data: {exc}; "
                    "time scrubber disabled.",
                    file=sys.stderr,
                )
                time_labels = None

    controls = _controls_strip_snippet(
        fig_id=fig_id,
        show_lock_btn=True,
        show_orientation=True,
        time_labels=time_labels,
        time_data_b64=time_data_b64,
        time_global_range=time_global_range,
        time_field=scalar_name,
    )
    if controls:
        html = out_html.read_text(encoding="utf-8")
        if "</body>" in html:
            out_html.write_text(html.replace("</body>", controls + "\n</body>", 1),
                                encoding="utf-8")


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
    if ncols < 1 or nrows < 1:
        raise ValueError(
            f"[4dpaper] 4d-panel layout dimensions must be positive integers, got: '{layout}'"
        )

    height = panel.get("height", "800px")

    # Generate each sub-figure HTML (reuses caching inside generate_html_figure)
    is_timeseries = panel.get("timeseries", False)
    camera_mode = panel.get("camera_mode", "independent")

    for sub_idx, sub in enumerate(panel["subfigures"]):
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        out = figures_dir / f"{sub['id']}.html"
        af = [f.strip() for f in sub.get("fields", "").split(",") if f.strip()] or None
        # For timeseries: only show colorbar and lock button on the first panel
        # For sync-mode panels: never show lock button (panel-level toolbar handles it)
        is_first = sub_idx == 0
        generate_html_figure(
            src, sub["field"], sub["time"], out, fig_id=sub["id"], available_fields=af,
            show_colorbar=is_first if is_timeseries else True,
            show_lock_btn=(is_first if is_timeseries else True) and camera_mode != "sync",
            show_orientation=is_first if is_timeseries else True,
        )

    # Bidirectional re-relay: forwards camera/field UP to top, acks DOWN to children
    panel_id = panel["id"]

    # 1. Process JS template from asset
    js_tmpl = get_asset("panel_sync.js")
    re_relay = f"<script>\n{js_tmpl.replace('{{PANEL_ID}}', panel_id).replace('{{SYNC_MODE}}', 'true' if camera_mode == 'sync' else 'false')}\n</script>"

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
    out_path.write_text(composite)
    print(f"[4dpaper] Generated panel (HTML): {out_path}", file=sys.stderr)

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
    print(f"[4dpaper] Wrote manifest: {manifest_path}", file=sys.stderr)


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
            f"[4dpaper] 4d-panel layout must be 'COLSxROWS' (e.g. '2x2', '3x1'), got: '{layout}'"
        )
    if ncols < 1 or nrows < 1:
        raise ValueError(
            f"[4dpaper] 4d-panel layout dimensions must be positive integers, got: '{layout}'"
        )

    camera_mode = panel.get("camera_mode", "independent")
    is_timeseries = panel.get("timeseries", False)
    # Generate each sub-figure PNG
    for sub_idx, sub in enumerate(panel["subfigures"]):
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        out = figures_dir / f"{sub['id']}.png"
        cam_id = panel["id"] if camera_mode == "sync" else sub["id"]
        show_cb = (sub_idx == 0) if is_timeseries else True
        generate_png_figure(src, sub["field"], sub["time"], out,
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
    print(f"[4dpaper] Generated panel (PNG): {out_path}")


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
        print(f"[4dpaper] Generated (frame PNG): {frame_path}", file=sys.stderr)

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
            f"[4dpaper] Warning: could not generate preview for {fig_id}: {exc}.",
            file=sys.stderr,
        )

    # Build self-contained HTML document with base64-encoded MP4 data URI
    b64 = base64.b64encode(mp4_path.read_bytes()).decode("ascii")
    video_html = _build_video_html_fragment(b64, fig_id)
    video_html_path.parent.mkdir(parents=True, exist_ok=True)
    video_html_path.write_text(video_html)
    print(f"[4dpaper] Generated (video HTML): {video_html_path}", file=sys.stderr)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_quarto_pre_render() -> None:
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
        # Scan root *.qmd files and all *.qmd files in sections/ and subdirectories
        qmd_files = sorted(project_dir.glob("*.qmd"))
        qmd_files.extend(sorted(project_dir.glob("sections/**/*.qmd")))
        if not qmd_files:
            print("[4dpaper] No .qmd files found — skipping.", file=sys.stderr)
            return
        print(f"[4dpaper] Scanning {len(qmd_files)} QMD file(s) in {project_dir}", file=sys.stderr)

    figures = []
    videos = []
    panels = []
    pvsm_figs = []
    ts_raw = []
    graphs = []
    for qmd in qmd_files:
        text = qmd.read_text()
        figures.extend(parse_shortcodes(text))
        videos.extend(parse_video_shortcodes(text))
        panels.extend(parse_panel_shortcodes(text))
        pvsm_figs.extend(parse_pvsm_shortcodes(text))
        ts_raw.extend(parse_timeseries_shortcodes(text))
        graphs.extend(parse_graph_shortcodes(text))

    if not any([figures, videos, panels, pvsm_figs, ts_raw, graphs]):
        print("[4dpaper] No 4d-image, 4d-video, 4d-panel, 4d-pvsm, 4d-timeseries, or 4d-graph shortcodes found.", file=sys.stderr)
        return

    figures_dir = _project_root / "state" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Load style templates once for all figures
    styles_yml_path = _project_root / "_4dpaper_styles.yml"
    styles_config = load_styles(styles_yml_path)
    styles_extra_deps = [styles_yml_path] if styles_yml_path.exists() else []

    # Expand timeseries into panel-compatible dicts and merge into panels list
    if ts_raw:
        from scripts.data_loader import SimulationData as _SimData  # noqa: PLC0415
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

    for fig in figures:
        fig_id = fig["id"]
        src = Path(fig["src"]) if Path(fig["src"]).is_absolute() else _project_root / fig["src"]
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
        if not script_newer and is_cache_valid(out_html, src, field_path=field_state_path, extra_deps=styles_extra_deps):
            print(f"[4dpaper] {fig_id}.html is up to date — skipping.", file=sys.stderr)
        else:
            print(f"[4dpaper] Generating {fig_id}.html …", file=sys.stderr)
            try:
                generate_html_figure(
                    src, field, time_spec, out_html,
                    fig_id=fig_id, available_fields=available_fields,
                    background=style["background"],
                    axis_color=style["axis_color"],
                    cmap=style["cmap"],
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
                _log(f"Camera for {fig_id}: file exists but is invalid — will use isometric view", level="WARN")
        else:
            _log(
                f"Camera for {fig_id}: NOT SET — isometric view will be used. "
                "Rotate the figure in the HTML preview to save a camera position.", 
                level="INFO"
            )
        # Always regenerate PNG when a camera file exists...
        png_fresh = is_cache_valid(out_png, src, camera_path=camera_path, field_path=field_state_path, extra_deps=styles_extra_deps)
        if png_fresh:
            _log(f"{fig_id}.png is up to date — skipping.")
        else:
            _log(f"Generating {fig_id}.png …")
            try:
                generate_png_figure(
                    src, field, time_spec, out_png, fig_id=fig_id,
                    background=style["background"],
                    axis_color=style["axis_color"],
                    cmap=style["cmap"],
                )
            except Exception as exc:
                _log(f"could not generate {fig_id}.png: {exc}", level="WARN")
                _log("  PNG is needed for PDF export only — HTML render continues.", level="DEBUG")

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
            _log(f"{fig_id} video outputs are up to date — skipping.")
            continue

        _log(f"Generating video for {fig_id} …")
        try:
            generate_video_figure(
                src, field, fps, time_spec,
                mp4_path, frame_path, video_html_path,
                fig_id=fig_id,
                preview_html_path=preview_html_path,
            )
        except Exception as exc:
            _log(f"ERROR generating video {fig_id}: {exc}", level="ERROR")
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

        if out_html.exists() and out_html.stat().st_mtime >= max_dep_mtime:
            _log(f"{panel_id}.html is up to date — skipping.")
        else:
            _log(f"Generating panel {panel_id}.html …")
            try:
                generate_panel_html(panel, figures_dir)
            except Exception as exc:
                _log(f"ERROR generating panel {panel_id}.html: {exc}", level="ERROR")
                sys.exit(1)

        if out_png.exists() and out_png.stat().st_mtime >= max_dep_mtime:
            _log(f"{panel_id}.png is up to date — skipping.")
        else:
            _log(f"Generating panel {panel_id}.png …")
            try:
                generate_panel_png(panel, figures_dir)
            except Exception as exc:
                _log(f"ERROR generating panel {panel_id}.png: {exc}", level="ERROR")
                sys.exit(1)

    # -- PVSM shortcode processing -----------------------------------------------
    _pvsm_render_script = _ext_dir / "pvsm_render.py"
    _pvpython_path = find_pvpython()
    
    # Pre-flight check for ParaView version if PVSM figures are present
    if pvsm_figs and not check_paraview_version("6.0.1", pvpython_path=_pvpython_path):
        _log("ParaView version check failed. PVSM rendering may be skipped or fail.", level="WARN")

    for pvsm_fig in pvsm_figs:
        fig_id   = pvsm_fig["id"]
        pvsm_src = Path(pvsm_fig["src"]) if Path(pvsm_fig["src"]).is_absolute() \
                   else _project_root / pvsm_fig["src"]
        data_str = pvsm_fig.get("data", "").strip()
        data_path = Path(data_str) if data_str else None
        time_spec = pvsm_fig.get("time", "").strip() or None

        out_html    = figures_dir / f"{fig_id}.html"
        out_png     = figures_dir / f"{fig_id}.png"
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"

        extra_deps = [_pvsm_render_script]
        script_newer = out_html.exists() and _here.stat().st_mtime > out_html.stat().st_mtime

        # time_spec figures render a single frame; no per-step bins to check.
        scalar_bins_ok = True
        if not time_spec:
            times_json_path = figures_dir / f"{fig_id}-times.json"
            if times_json_path.exists():
                try:
                    n_steps = len(json.loads(times_json_path.read_text(encoding="utf-8")))
                    bin_paths = [
                        figures_dir / f"{fig_id}-scalars-t{i}.bin"
                        for i in range(n_steps)
                    ]
                    scalar_bins_ok = all(
                        is_cache_valid(p, pvsm_src, camera_path=camera_path)
                        for p in bin_paths
                    )
                except (OSError, ValueError):
                    scalar_bins_ok = False
            else:
                scalar_bins_ok = False

        cache_ok = (
            not script_newer
            and scalar_bins_ok
            and is_cache_valid(out_html, pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
            and is_cache_valid(out_png,  pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
        )

        if cache_ok:
            _log(f"{fig_id} PVSM outputs are up to date -- skipping.")
            continue

        _log(f"Generating PVSM figure for {fig_id} ...")
        try:
            generate_pvsm_figure(
                pvsm_path=pvsm_src,
                fig_id=fig_id,
                figures_dir=figures_dir,
                data_path=data_path,
                time_spec=time_spec,
                pvpython_path=_pvpython_path,
            )
        except Exception as exc:
            _log(f"ERROR generating PVSM figure {fig_id}: {exc}", level="ERROR")
            sys.exit(1)

    for graph in graphs:
        fig_id = graph["id"]
        src = Path(graph["src"]) if Path(graph["src"]).is_absolute() else _project_root / graph["src"]
        
        out_html = figures_dir / f"{fig_id}.html"
        out_png = figures_dir / f"{fig_id}.png"
        
        script_newer = out_html.exists() and _here.stat().st_mtime > out_html.stat().st_mtime
        cache_ok = (
            not script_newer
            and is_cache_valid(out_html, src)
            and is_cache_valid(out_png, src)
        )
        
        if cache_ok:
            _log(f"{fig_id} Graph outputs are up to date -- skipping.")
            continue
            
        _log(f"Generating Graph figure for {fig_id} ({src}) ...")
        try:
            import plotly.io as pio
            import plotly.graph_objects as go
            
            with open(src, "r") as f:
                fig_dict = json.load(f)
            
            fig = go.Figure(fig_dict)
            
            pio.write_image(fig, out_png, format="png", engine="kaleido", scale=2)
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

            html_content = pio.to_html(fig, full_html=True, include_plotlyjs="cdn", config={'displayModeBar': False})
            inj_html = _controls_strip_snippet(fig_id, show_orientation=False)
            if '</body>' in html_content:
                html_content = html_content.replace('</body>', inj_html + '\n</body>', 1)
            else:
                html_content += inj_html
                
            out_html.write_text(html_content, encoding="utf-8")
        except Exception as exc:
            _log(f"ERROR generating Graph figure {fig_id}: {exc}", level="ERROR")
            sys.exit(1)


def run_audit() -> None:
    """
    Perform a comprehensive diagnostic of the 4DPaper environment.
    Reports versions of core dependencies and performs a headless render test.
    """
    _log("── 4DPaper Environment Audit ──", level="AUDIT")
    
    # 1. System Info
    _log(f"OS: {platform.platform()} ({platform.machine()})")
    _log(f"Python: {sys.version.splitlines()[0]}")
    _log(f"Executable: {sys.executable}")
    
    # 2. Dependency Check
    deps = ["vtk", "pyvista", "numpy", "matplotlib", "yaml"]
    for d in deps:
        try:
            mod = __import__(d)
            v = getattr(mod, "__version__", "unknown")
            _log(f"{d:12}: {v}")
        except ImportError:
            _log(f"{d:12}: MISSING", level="ERROR")

    # 3. Graphics Stack (Headless Render Test)
    _log("Testing Graphics Stack (Headless Render)...")
    try:
        import pyvista as pv
        pv.OFF_SCREEN = True
        pl = pv.Plotter(off_screen=True)
        pl.add_mesh(pv.Sphere())
        pl.render()
        pl.close()
        _log("Graphics Stack: OK (Off-screen rendering functional)")
    except Exception as exc:
        _log(f"Graphics Stack: FAILED ({exc})", level="ERROR")
        _log("Note: Hardware acceleration might be missing or misconfigured.", level="WARN")

    # 4. ParaView Discovery
    _log("Searching for ParaView (pvpython)...")
    pv_path = find_pvpython()
    if pv_path:
        _log(f"pvpython: Found at {pv_path}")
        try:
            # Try to get version from pvpython
            cmd = [str(pv_path), "-c", "import paraview.servermanager as sm; print(sm.vtkSMProxyManager.GetParaViewSourceVersion())"]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=5).decode().strip()
            _log(f"ParaView: {out}")
        except Exception as exc:
            _log(f"ParaView: Found but version check failed ({exc})", level="WARN")
    else:
        _log("pvpython: NOT FOUND (PVSM figures will be skipped)", level="WARN")

    _log("── Audit Complete ──", level="AUDIT")


def main() -> None:
    # 1. Handle --audit flag immediately
    if "--audit" in sys.argv:
        run_audit()
        sys.exit(0)

    action = sys.argv[1] if len(sys.argv) > 1 else "render"
    
    if action == "render":
        run_quarto_pre_render()
    elif action == "camera-lock":
        # Placeholder for future dashboard camera locking logic
        _log("Action 'camera-lock' requested (not yet fully implemented)")
    else:
        _log(f"Unknown action: {action}", level="ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
