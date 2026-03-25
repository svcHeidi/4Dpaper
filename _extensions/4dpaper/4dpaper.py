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
        kwargs.setdefault("style", "")   # named style template
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
                "src":    kwargs[f"src{n}"],
                "id":     kwargs.get(f"id{n}", f"panel-sub-{n}"),
                "field":  kwargs.get(f"field{n}", ""),
                "time":   kwargs.get(f"time{n}", "mid"),
                "fields": kwargs.get(f"fields{n}", ""),
            })
            n += 1
        if not subfigures:
            print(f"[4dpaper] Warning: 4d-panel '{kwargs['id']}' has no sub-figures — skipping.", file=sys.stderr)
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


# -- Timeseries parsing ----------------------------------------------------------

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


# -- PVSM parsing ---------------------------------------------------------------

def parse_pvsm_shortcodes(text: str) -> list[dict]:
    """
    Parse {{< 4d-pvsm key="value" ... >}} shortcodes from QMD text.

    Required: id, src. Optional: data, time, caption.
    Shortcodes missing 'id' or 'src' are silently skipped.
    """
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-pvsm\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("data", "")
        kwargs.setdefault("time", "")
        kwargs.setdefault("caption", "")
        results.append(kwargs)
    return results


def parse_pvsm_color_info(pvsm_path: Path) -> dict:
    """
    Extract color/scalar info from a ParaView state (.pvsm) XML file.

    Returns a dict with keys:
      scalar_name      : str   -- active array name (empty string if not found)
      field_association: str   -- 'point' or 'cell'
      vmin             : float -- scalar range minimum
      vmax             : float -- scalar range maximum
      cmap             : str or matplotlib colormap -- color map for PyVista
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

        # -- Find the leaf (terminal) visible source proxy id ---------------------
        # Walk all representation proxies (any type) that have both an Input
        # and a ColorArrayName property; pick the last one in XML order.
        leaf_rep_proxy = None
        for proxy in sms.findall("Proxy[@group='representations']"):
            inp_prop = proxy.find("Property[@name='Input']")
            if inp_prop is None:
                continue
            inp_proxy_elem = inp_prop.find("Proxy")
            if inp_proxy_elem is None:
                continue
            # Must have a ColorArrayName property to be useful
            color_prop_check = proxy.find("Property[@name='ColorArrayName']")
            if color_prop_check is None:
                continue
            leaf_rep_proxy = proxy

        if leaf_rep_proxy is None:
            return _FALLBACK.copy()

        # -- Extract ColorArrayName -----------------------------------------------
        scalar_name = ""
        field_association = "point"
        color_prop = leaf_rep_proxy.find("Property[@name='ColorArrayName']")
        if color_prop is not None:
            elems = color_prop.findall("Element")
            if len(elems) >= 5:
                assoc_val = elems[3].get("value", "1")
                field_association = "point" if assoc_val == "1" else "cell"
                scalar_name = elems[4].get("value", "")

        # -- Find LookupTable proxy id --------------------------------------------
        lut_id = ""
        lut_prop = leaf_rep_proxy.find("Property[@name='LookupTable']")
        if lut_prop is not None:
            lut_proxy_elem = lut_prop.find("Proxy")
            if lut_proxy_elem is not None:
                lut_id = lut_proxy_elem.get("value", "")

        # -- Extract scalar range + color map from LookupTable --------------------
        vmin, vmax = 0.0, 1.0
        cmap = "coolwarm"

        if lut_id:
            lut_proxy = sms.find(f"Proxy[@id='{lut_id}']")
            if lut_proxy is not None:
                # RGBPoints: flat list [scalar, R, G, B, ...]
                rgb_prop = lut_proxy.find("Property[@name='RGBPoints']")
                if rgb_prop is not None:
                    vals = [float(e.get("value", 0)) for e in rgb_prop.findall("Element")]
                    if len(vals) >= 8:  # at least 2 control points
                        groups = [vals[i:i+4] for i in range(0, len(vals), 4)]
                        vmin = groups[0][0]
                        vmax = groups[-1][0]

                        # Try named preset first
                        preset_prop = lut_proxy.find("Property[@name='NameOfLastPresetApplied']")
                        preset_name = ""
                        if preset_prop is not None:
                            elem = preset_prop.find("Element")
                            if elem is not None:
                                preset_name = elem.get("value", "")

                        if preset_name and preset_name in _PRESET_MAP:
                            cmap = _PRESET_MAP[preset_name]
                        else:
                            # Build colormap from RGBPoints control points
                            span = vmax - vmin if vmax != vmin else 1.0
                            norm_colors = [
                                ((g[0] - vmin) / span, (g[1], g[2], g[3]))
                                for g in groups
                            ]
                            cmap = LinearSegmentedColormap.from_list(
                                "pvsm",
                                [(t, c) for t, c in norm_colors],
                            )

        return {
            "scalar_name": scalar_name,
            "field_association": field_association,
            "vmin": vmin,
            "vmax": vmax,
            "cmap": cmap,
        }

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
    Return True if fig_path exists, is newer than src_path, camera_path,
    field_path, and all extra_deps (if given and present).

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
    for dep in (extra_deps or []):
        if dep.exists() and fig_mtime <= dep.stat().st_mtime:
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

    The figure surface has zero UI overlay — all controls live in the strip.
    Exactly one panel is open at a time; clicking the active icon closes it.

    Replaces _camera_sync_snippet, _field_sync_snippet, _time_sync_snippet,
    and _orientation_snippet.
    """
    fig_id_js = json.dumps(fig_id).replace("</", "<\\/")
    fig_id_safe = fig_id.replace("</", "<\\/").replace('"', '').replace("-", "_")

    has_fields = bool(fields_to_embed and len(fields_to_embed) > 1)
    has_time = bool(time_labels and len(time_labels) > 1 and time_data_b64)
    n_time = len(time_data_b64) if time_data_b64 else 0

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

    corner_widget = ""
    if show_orientation:
        corner_widget = (
            f'<div id="cs-corner-{fig_id_safe}"'
            f' style="position:fixed;bottom:4px;left:4px;z-index:9999;">\n'
            f'  <svg id="cs-svg-axes-{fig_id_safe}" width="72" height="72"'
            f' style="background:rgba(10,10,20,0.55);border:1px solid rgba(255,255,255,0.12);'
            f'border-radius:4px;display:block;cursor:pointer;"'
            f' title="Click face for ortho view \u00b7 click corner for iso view"></svg>\n'
            f'</div>\n'
        )

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
            f' style="display:none;position:fixed;top:4px;right:36px;z-index:9999;'
            f'background:rgba(20,20,30,0.88);'
            f'border:1px solid rgba(255,255,255,0.12);'
            f'border-radius:4px;padding:2px 6px;'
            f'font-family:monospace;font-size:10px;color:#f88;">locked</div>\n'
        )

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

    html_block = ""
    if strip_btns:
        html_block += (
            f'<div id="cs-strip-{fig_id_safe}" style="position:fixed;right:4px;top:50%;'
            f'transform:translateY(-50%);z-index:9999;display:flex;flex-direction:column;gap:4px;">\n'
            + strip_btns
            + f'</div>\n'
        )
    html_block += lock_widget + lock_badge + field_pop + time_pop + corner_widget

    active_field_js = json.dumps(active_field).replace("</", "<\\/")
    field_data_js = json.dumps(field_data_b64 or {}).replace("</", "<\\/")
    field_ranges_js = json.dumps(field_ranges or {}).replace("</", "<\\/")
    time_field_js = json.dumps(time_field or active_field).replace("</", "<\\/")
    time_data_js = json.dumps(time_data_b64 or []).replace("</", "<\\/")
    time_labels_js = json.dumps(time_labels or []).replace("</", "<\\/")
    global_range_js = json.dumps(time_global_range or [0.0, 1.0])

    _js = []

    _js.append(f'  var FIG_ID={fig_id_js};\n')

    if show_orientation:
        _js.append(f'  var _iact=null;\n')

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
        + f'  }};\n'
    )

    # _locked ALWAYS declared (used by _sendCam regardless of show_lock_btn)
    _js.append(f'  var _locked=false;\n')
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

    # postMessage listener (always emitted)
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

    # sendCam (always emitted)
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
        f'          .catch(function(){{}});\n'
        f'      }}\n'
        f'    }},300);\n'
        f'  }}\n'
    )

    # Orientation helpers (conditional)
    if show_orientation:
        _cube_lock_gate = (
            f'if(_locked){{_showLockedBadge();return;}}'
        ) if show_lock_btn else ''
        _js.append(
            f'  var _renderer=null;\n'
            f'  function _n3(v){{var l=Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);'
            f'return l<1e-10?[0,0,1]:[v[0]/l,v[1]/l,v[2]/l];}}\n'
            f'  function _cr(a,b){{return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}}\n'
            f'  function _dt(a,b){{return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}}\n'
            f'  var _FACES=[\n'
            f'    {{verts:[[0.75,0.75,1],[0.75,-0.75,1],[-0.75,-0.75,1],[-0.75,0.75,1]],'
            f'normal:[0,0,1],fill:"#3a3aaa",stroke:"#6666dd",dir:[0,0,1]}},\n'
            f'    {{verts:[[0.75,0.75,-1],[0.75,-0.75,-1],[-0.75,-0.75,-1],[-0.75,0.75,-1]],'
            f'normal:[0,0,-1],fill:"#222266",stroke:"#4444aa",dir:[0,0,-1]}},\n'
            f'    {{verts:[[1,0.75,0.75],[1,-0.75,0.75],[1,-0.75,-0.75],[1,0.75,-0.75]],'
            f'normal:[1,0,0],fill:"#8a2222",stroke:"#cc5555",dir:[1,0,0]}},\n'
            f'    {{verts:[[-1,0.75,0.75],[-1,-0.75,0.75],[-1,-0.75,-0.75],[-1,0.75,-0.75]],'
            f'normal:[-1,0,0],fill:"#441111",stroke:"#883333",dir:[-1,0,0]}},\n'
            f'    {{verts:[[0.75,1,0.75],[-0.75,1,0.75],[-0.75,1,-0.75],[0.75,1,-0.75]],'
            f'normal:[0,1,0],fill:"#1e6b1e",stroke:"#44aa44",dir:[0,1,0]}},\n'
            f'    {{verts:[[0.75,-1,0.75],[-0.75,-1,0.75],[-0.75,-1,-0.75],[0.75,-1,-0.75]],'
            f'normal:[0,-1,0],fill:"#0d3d0d",stroke:"#226622",dir:[0,-1,0]}},\n'
            f'  ];\n'
            f'  var _CORNERS=[\n'
            f'    {{verts:[[0.75,1,1],[1,0.75,1],[1,1,0.75]],normal:[1,1,1],dir:[1,1,1]}},\n'
            f'    {{verts:[[0.75,1,-1],[1,0.75,-1],[1,1,-0.75]],normal:[1,1,-1],dir:[1,1,-1]}},\n'
            f'    {{verts:[[0.75,-1,1],[1,-0.75,1],[1,-1,0.75]],normal:[1,-1,1],dir:[1,-1,1]}},\n'
            f'    {{verts:[[-0.75,1,1],[-1,0.75,1],[-1,1,0.75]],normal:[-1,1,1],dir:[-1,1,1]}},\n'
            f'    {{verts:[[0.75,-1,-1],[1,-0.75,-1],[1,-1,-0.75]],normal:[1,-1,-1],dir:[1,-1,-1]}},\n'
            f'    {{verts:[[-0.75,1,-1],[-1,0.75,-1],[-1,1,-0.75]],normal:[-1,1,-1],dir:[-1,1,-1]}},\n'
            f'    {{verts:[[-0.75,-1,1],[-1,-0.75,1],[-1,-1,0.75]],normal:[-1,-1,1],dir:[-1,-1,1]}},\n'
            f'    {{verts:[[-0.75,-1,-1],[-1,-0.75,-1],[-1,-1,-0.75]],normal:[-1,-1,-1],dir:[-1,-1,-1]}},\n'
            f'  ];\n'
            f'  var _svg=null;\n'
            f'  function _drawCube(){{\n'
            f'    if(!_renderer||!_svg)return;\n'
            f'    var cam=_renderer.getActiveCamera();\n'
            f'    var pos=cam.getPosition(),fp=cam.getFocalPoint(),vup=cam.getViewUp();\n'
            f'    var vd=_n3([fp[0]-pos[0],fp[1]-pos[1],fp[2]-pos[2]]);\n'
            f'    var right=_n3(_cr(vd,vup));\n'
            f'    var up=_cr(right,vd);\n'
            f'    var cx=36,cy=36,R=28;\n'
            f'    function proj(v){{return[cx+R*_dt(v,right),cy-R*_dt(v,up)];}}\n'
            f'    function depth(verts){{var d=0;for(var i=0;i<verts.length;i++)d+=_dt(verts[i],vd);return d/verts.length;}}\n'
            f'    var pieces=[];\n'
            f'    _FACES.forEach(function(f){{\n'
            f'      if(_dt(f.normal,vd)>0.05)\n'
            f'        pieces.push({{verts:f.verts,fill:f.fill,stroke:f.stroke,dir:f.dir,depth:depth(f.verts)}});\n'
            f'    }});\n'
            f'    _CORNERS.forEach(function(c){{\n'
            f'      if(_dt(c.normal,vd)>0.05)\n'
            f'        pieces.push({{verts:c.verts,fill:"#c8a800",stroke:"#ffe033",dir:c.dir,depth:depth(c.verts)}});\n'
            f'    }});\n'
            f'    pieces.sort(function(a,b){{return a.depth-b.depth;}});\n'
            f'    var html="";\n'
            f'    pieces.forEach(function(p){{\n'
            f'      var pts=p.verts.map(function(v){{var s=proj(v);return s[0].toFixed(1)+","+s[1].toFixed(1);}}).join(" ");\n'
            f'      html+=\'<polygon points="\'+pts+\'" fill="\'+p.fill+\'" stroke="\'+p.stroke+\'" stroke-width="1.5"\'\n'
            f'           +\' style="cursor:pointer;"\'\n'
            f'           +\' onclick="{_cube_lock_gate}csSetView_{fig_id_safe}([\'+p.dir[0]+\',\'+p.dir[1]+\',\'+p.dir[2]+\'])"/>\';'
            f'\n'
            f'    }});\n'
            f'    _svg.innerHTML=html;\n'
            f'  }}\n'
            f'  function _axLoop(){{_drawCube();requestAnimationFrame(_axLoop);}}\n'
            f'  window.csSetView_{fig_id_safe}=function(dir){{\n'
            f'    if(!_renderer)return;\n'
            f'    var cam=_renderer.getActiveCamera();\n'
            f'    var fp=cam.getFocalPoint(),dist=cam.getDistance();\n'
            f'    var pn=_n3(dir);\n'
            f'    var up=(Math.abs(pn[2])>0.9)?[0,1,0]:[0,0,1];\n'
            f'    cam.setPosition(fp[0]+pn[0]*dist,fp[1]+pn[1]*dist,fp[2]+pn[2]*dist);\n'
            f'    cam.setViewUp(up[0],up[1],up[2]);\n'
            f'    cam.setFocalPoint(fp[0],fp[1],fp[2]);\n'
            f'    _renderer.resetCameraClippingRange();\n'
            f'    if(_iact)_iact.setEnabled(1);\n'
            f'    if(window.renderWindow)window.renderWindow.render();\n'
            f'  }};\n'
        )
    else:
        _js.append(f'  var _renderer=null;\n')

    # Renderer polling
    _svg_assign = (
        f'          _svg=document.getElementById("cs-svg-axes-{fig_id_safe}");\n'
    ) if show_orientation else ''
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
        + _svg_assign
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
            f'              var b64=TIME_DATA[idx];if(!b64)return;\n'
            f'              try{{var a=pd.getPointData().getArrayByName(TIME_FIELD);\n'
            f'a.setData(_decT(b64),1);a.modified();pd.modified();\n'
            f'mp.setScalarRange(GLOBAL_RANGE[0],GLOBAL_RANGE[1]);\n'
            f'window.renderWindow.render();}}'
            f'catch(e1){{console.error("[4dp] t-step:",e1);}}\n'
            f'              _tTimer=setTimeout(function(){{\n'
            f'                try{{parent.postMessage({{type:"4dpaper-field-update",'
            f'fig_id:FIG_ID,data:{{time:String(idx)}}}},"*");}}'
            f'catch(e2){{}}\n'
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

    pl = pv.Plotter(off_screen=True, window_size=(1920, 1080))
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
    Generate HTML + PNG figures from a ParaView state file.

    Step 1: pvpython subprocess -> {fig_id}-pipeline.vtu + {fig_id}.png
    Step 2: PyVista in-process -> {fig_id}.html + {fig_id}-preview.html
    """
    import subprocess

    if pvpython_path is None:
        pvpython_path = Path("/Applications/ParaView-6.0.1.app/Contents/bin/pvpython")
    if not pvpython_path.exists():
        raise RuntimeError(
            f"pvpython not found at {pvpython_path}. "
            "Set the correct path in config or install ParaView."
        )

    pvsm_render_script = _here.parent / "pvsm_render.py"
    out_vtu     = figures_dir / f"{fig_id}-pipeline.vtu"
    out_png     = figures_dir / f"{fig_id}.png"
    out_html    = figures_dir / f"{fig_id}.html"
    out_preview = figures_dir / f"{fig_id}-preview.html"
    camera_path = _project_root / "state" / f"camera_{fig_id}.json"

    # -- Step 1: pvpython subprocess -------------------------------------------
    cmd = [
        str(pvpython_path), str(pvsm_render_script),
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

    print(f"[4dpaper] Running pvpython for {fig_id} ...", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="", file=sys.stderr)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"pvpython failed for {fig_id} (exit {result.returncode}). "
            "See output above."
        )

    if not out_vtu.exists():
        raise RuntimeError(f"pvpython did not produce {out_vtu}")

    # -- Step 2: PyVista HTML export -------------------------------------------
    color_info = parse_pvsm_color_info(pvsm_path)

    print(f"[4dpaper] Generating {fig_id}.html from VTU ...", file=sys.stderr)
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

    print(f"[4dpaper] Generating {fig_id}-preview.html ...", file=sys.stderr)
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
    for sub_idx, sub in enumerate(panel["subfigures"]):
        src = Path(sub["src"]) if Path(sub["src"]).is_absolute() else _project_root / sub["src"]
        out = figures_dir / f"{sub['id']}.html"
        af = [f.strip() for f in sub.get("fields", "").split(",") if f.strip()] or None
        # For timeseries: only show colorbar and lock button on the first panel
        is_first = sub_idx == 0
        generate_html_figure(
            src, sub["field"], sub["time"], out, fig_id=sub["id"], available_fields=af,
            show_colorbar=is_first if is_timeseries else True,
            show_lock_btn=is_first if is_timeseries else True,
            show_orientation=is_first if is_timeseries else True,
        )

    # Bidirectional re-relay: forwards camera/field UP to top, acks DOWN to children
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
                print(f"[4dpaper] Camera for {fig_id}: file exists but is invalid — will use isometric view")
        else:
            print(
                f"[4dpaper] Camera for {fig_id}: NOT SET — isometric view will be used. "
                f"Rotate the figure in the HTML preview to save a camera position."
            )
        # Always regenerate PNG when a camera file exists...
        png_fresh = is_cache_valid(out_png, src, camera_path=camera_path, field_path=field_state_path, extra_deps=styles_extra_deps)
        if png_fresh:
            print(f"[4dpaper] {fig_id}.png is up to date — skipping.")
        else:
            print(f"[4dpaper] Generating {fig_id}.png …")
            try:
                generate_png_figure(
                    src, field, time_spec, out_png, fig_id=fig_id,
                    background=style["background"],
                    axis_color=style["axis_color"],
                    cmap=style["cmap"],
                )
            except Exception as exc:
                print(f"[4dpaper] WARNING: could not generate {fig_id}.png: {exc}")
                print(f"[4dpaper]   PNG is needed for PDF export only — HTML render continues.")

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
            print(f"[4dpaper] {panel_id}.html is up to date — skipping.", file=sys.stderr)
        else:
            print(f"[4dpaper] Generating panel {panel_id}.html …", file=sys.stderr)
            try:
                generate_panel_html(panel, figures_dir)
            except Exception as exc:
                print(f"[4dpaper] ERROR generating panel {panel_id}.html: {exc}", file=sys.stderr)
                sys.exit(1)

        if out_png.exists() and out_png.stat().st_mtime >= max_dep_mtime:
            print(f"[4dpaper] {panel_id}.png is up to date — skipping.")
        else:
            print(f"[4dpaper] Generating panel {panel_id}.png …")
            try:
                generate_panel_png(panel, figures_dir)
            except Exception as exc:
                print(f"[4dpaper] ERROR generating panel {panel_id}.png: {exc}")
                sys.exit(1)

    # -- PVSM shortcode processing -----------------------------------------------
    _pvsm_render_script = _here.parent / "pvsm_render.py"
    _pvpython_path = Path("/Applications/ParaView-6.0.1.app/Contents/bin/pvpython")

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
        cache_ok = (
            not script_newer
            and is_cache_valid(out_html, pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
            and is_cache_valid(out_png,  pvsm_src, camera_path=camera_path, extra_deps=extra_deps)
        )

        if cache_ok:
            print(f"[4dpaper] {fig_id} PVSM outputs are up to date -- skipping.", file=sys.stderr)
            continue

        print(f"[4dpaper] Generating PVSM figure for {fig_id} ...", file=sys.stderr)
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
            print(f"[4dpaper] ERROR generating PVSM figure {fig_id}: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
