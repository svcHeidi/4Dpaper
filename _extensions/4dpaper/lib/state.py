from __future__ import annotations
import sys
import json
from pathlib import Path
import os
try:
    import pyvista as pv
except ImportError:
    pass

_here = Path(__file__).resolve()
_project_root = Path(
    os.environ.get("PROJECT_ROOT")
    or os.environ.get("QUARTO_PROJECT_DIR")
    or str(_here.parent.parent.parent)
)

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

