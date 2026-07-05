from __future__ import annotations
import sys
import os
import time
import json
import base64 as _b64
from pathlib import Path
import concurrent.futures
try:
    import pyvista as pv
except ImportError:
    pass

from .config import _project_root
from .utils import resolve_src_path, _maybe_sign_output_html
from .state import _load_saved_field_state, apply_camera_state
from .mesh import _prepare_surface, _apply_decimation, _get_overlay_at_time, _merge_overlay_mesh, _add_mesh_auto, _has_polygon_cells
from .frontend import _controls_strip_snippet, _timeseries_sync_snippet, _multi_actor_extension_snippet, _build_video_html_fragment
from .timeseries import _nearest_time_idx

_DEFAULT_CMAPS = ["coolwarm", "plasma", "viridis", "RdBu"]

_COLORBAR_POSITIONS = [
    {"position_x": 0.85, "position_y": 0.05, "width": 0.10, "height": 0.22},
    {"position_x": 0.85, "position_y": 0.29, "width": 0.10, "height": 0.22},
    {"position_x": 0.85, "position_y": 0.53, "width": 0.10, "height": 0.22},
    {"position_x": 0.85, "position_y": 0.77, "width": 0.10, "height": 0.22},
]

_SIMULATION_CACHE = {}

_MAX_TIMELINE_FRAMES_LIGHT = 20
_MAX_TIMELINE_FRAMES_MEDIUM = 12
_MAX_TIMELINE_FRAMES_HEAVY = 8
_MAX_TIMELINE_FRAMES_EXTREME = 5

def _resolve_time_index(time_spec: str, n_steps: int) -> int:
    if time_spec == "first":
        return 0
    if time_spec == "last":
        return max(0, n_steps - 1)
    try:
        return max(0, min(int(time_spec), n_steps - 1))
    except (TypeError, ValueError):
        return n_steps // 2

def _frame_index_for_step(step_indices: list[int], step_idx: int) -> int:
    if not step_indices:
        return 0
    return min(range(len(step_indices)), key=lambda i: abs(step_indices[i] - step_idx))

def _mesh_has_field(mesh, field: str) -> bool:
    return bool(field) and (
        field in getattr(mesh, "point_data", {}) or field in getattr(mesh, "cell_data", {})
    )

def _multi_image_scalar_bar_args(
    field: str,
    axis_color: str,
    source_index: int,
    show_colorbar: bool,
) -> dict:
    """Match the primary figure colorbar and only hard-position overlay bars."""
    if not show_colorbar:
        return {}

    scalar_bar_args = {"title": field, "color": axis_color}
    if source_index == 0:
        return scalar_bar_args

    overlay_pos = _COLORBAR_POSITIONS[(source_index - 1) % len(_COLORBAR_POSITIONS)]
    return {**scalar_bar_args, **overlay_pos}

def _timeline_step_indices(sim, fields: list[str], stride: int) -> list[int]:
    step_indices = list(range(0, sim.n_steps, stride))
    primary_fields = [f for f in fields if f]
    if not primary_fields:
        return step_indices

    filtered: list[int] = []
    for idx in step_indices:
        mesh = sim.get_mesh(idx)
        if mesh is None:
            continue
        if all(_mesh_has_field(mesh, f) for f in primary_fields):
            filtered.append(idx)
    return filtered or step_indices

def _apply_timeline_frame_budget(
    step_indices: list[int],
    *,
    point_budget: int,
) -> tuple[list[int], int | None]:
    """Cap embedded timeline frames for large interactive payloads.

    `point_budget` is a coarse proxy for the amount of per-frame scalar payload
    we would inline into the generated HTML. The thresholds are intentionally
    conservative for cold Docker renders, where very large timeline payloads can
    fail before Quarto reaches the final document render.
    """
    if len(step_indices) <= 1:
        return step_indices, None

    if point_budget >= 120_000:
        max_frames = _MAX_TIMELINE_FRAMES_EXTREME
    elif point_budget >= 80_000:
        max_frames = _MAX_TIMELINE_FRAMES_HEAVY
    elif point_budget >= 40_000:
        max_frames = _MAX_TIMELINE_FRAMES_MEDIUM
    else:
        max_frames = _MAX_TIMELINE_FRAMES_LIGHT

    if len(step_indices) <= max_frames:
        return step_indices, None

    if max_frames <= 1:
        return [step_indices[0]], max_frames

    picks = []
    last = len(step_indices) - 1
    for i in range(max_frames):
        pos = round(i * last / (max_frames - 1))
        picks.append(step_indices[pos])

    # Preserve order while removing any duplicate positions introduced by rounding.
    capped = list(dict.fromkeys(picks))
    return capped, max_frames

def _sample_on_reference(reference, mesh):
    if reference is None:
        return _prepare_surface(mesh)
    surface = reference.copy()
    surface.clear_data()
    return surface.sample(mesh)

def _html_time_frame_count(path: Path) -> int:
    if not path.exists():
        return 0
    html = path.read_text(encoding="utf-8", errors="ignore")
    marker = "TIME_LABELS="
    start = html.find(marker)
    if start < 0:
        return 0
    start += len(marker)
    end = html.find(", TIME_GLOBAL_RANGE=", start)
    if end < 0:
        return 0
    try:
        labels = json.loads(html[start:end])
    except json.JSONDecodeError:
        return 0
    return len(labels) if isinstance(labels, list) else 0

def _panel_transport_html(
    panel_id: str,
    frame_count: int,
    actual_indices: list[int] | None = None,
) -> str:
    actual_indices = [int(v) for v in (actual_indices or [])]
    transport_count = len(actual_indices) if actual_indices else frame_count
    transport = ""
    actual_json = json.dumps(actual_indices)
    if transport_count > 1:
        transport = f"""
<div style="display:flex;align-items:center;gap:6px;min-width:220px;flex:1;">
  <button id="plb-play-{panel_id}" title="Play / pause synchronized animation" style="width:22px;height:22px;background:#25201c;border:1px solid #4a4138;color:#e8e2dc;border-radius:3px;cursor:pointer;font-size:11px;line-height:1;">&#x25B6;</button>
  <input id="plb-time-{panel_id}" title="Synchronized frame" type="range" min="0" max="{transport_count - 1}" value="0" style="flex:1;min-width:120px;height:4px;accent-color:#9d7a48;">
  <span id="plb-time-val-{panel_id}" style="color:#b8aea4;font-size:10px;font-variant-numeric:tabular-nums;min-width:42px;text-align:right;">1/{transport_count}</span>
</div>"""
    return f"""
<div id="plb-{panel_id}" style="display:flex;align-items:center;justify-content:flex-end;gap:8px;background:#181614;border-bottom:1px solid #3d3834;padding:3px 8px;font-family:system-ui,sans-serif;font-size:11px;">
{transport}
  <button id="plb-btn-{panel_id}" title="Lock / unlock panel cameras" style="background:none;border:none;cursor:pointer;font-size:14px;padding:0;line-height:1;">&#x1F513;</button>
</div>
<script>
(function(){{
var PID="{panel_id}",N={transport_count},ACTUAL={actual_json},_pl=false,_idx=0,_tm=0,_locked=false;
function _fs(){{return document.querySelectorAll('iframe[data-panel="'+PID+'"]');}}
function _bc(v){{var f=_fs();for(var i=0;i<f.length;i++)f[i].contentWindow.postMessage({{type:"4dpaper-lock-all",locked:v}},"*");}}
function _bh(){{var f=_fs();for(var i=0;i<f.length;i++)f[i].contentWindow.postMessage({{type:"4dpaper-hide-lock-btn"}},"*");}}
function _actual(i){{return ACTUAL.length?ACTUAL[i]:i;}}
function _fromActual(i){{if(!ACTUAL.length)return i;var best=0,bestDiff=Math.abs(ACTUAL[0]-i);for(var j=1;j<ACTUAL.length;j++){{var d=Math.abs(ACTUAL[j]-i);if(d<bestDiff){{best=j;bestDiff=d;}}}}return best;}}
function _send(i){{var actual=_actual(i);var f=_fs();for(var j=0;j<f.length;j++)f[j].contentWindow.postMessage({{type:"4dpaper-time-apply",fig_id:PID,idx:i,source_idx:actual,playing:false}},"*");}}
function _label(){{var l=document.getElementById("plb-time-val-"+PID);if(l&&N>1)l.textContent=(_idx+1)+"/"+N;}}
function _ui(i){{if(N<2)return;_idx=Math.max(0,Math.min(parseInt(i||0,10)||0,N-1));var s=document.getElementById("plb-time-"+PID);if(s)s.value=String(_idx);_label();}}
function _seek(i){{_ui(i);_send(_idx);}}
function _play(v){{if(N<2)return;_pl=!!v;var b=document.getElementById("plb-play-"+PID);if(b)b.innerHTML=_pl?"&#x23F8;":"&#x25B6;";if(_tm){{clearInterval(_tm);_tm=0;}}if(_pl){{_seek(_idx);_tm=setInterval(function(){{_seek((_idx+1)%N);}},180);}}}}
function _spl(v){{_locked=!!v;var b=document.getElementById("plb-btn-"+PID);if(b)b.innerHTML=_locked?"&#x1F512;":"&#x1F513;";_bc(_locked);}}
var pb=document.getElementById("plb-play-"+PID);if(pb)pb.addEventListener("click",function(){{_play(!_pl);}});
var sl=document.getElementById("plb-time-"+PID);if(sl)sl.addEventListener("input",function(){{_play(false);_seek(this.value);}});
window.addEventListener("message",function(e){{if(!e.data||e.data.type!=="4dpaper-time")return;var v=e.data.source_idx!=null?e.data.source_idx:e.data.idx;_ui(_fromActual(parseInt(v||0,10)||0));}});
var _iv=setInterval(_bh,500);setTimeout(function(){{clearInterval(_iv);}},8000);
var btn=document.getElementById("plb-btn-"+PID);if(btn)btn.addEventListener("click",function(){{_spl(!_locked);}});
_label();
}})();
</script>"""

def _get_simulation(src_path: Path):
    from scripts.data_loader import SimulationData
    key = str(src_path.resolve())
    if key not in _SIMULATION_CACHE:
        _SIMULATION_CACHE[key] = SimulationData(str(src_path)).load()
    return _SIMULATION_CACHE[key]

def generate_multi_image_html(
    sources: list[dict],
    time_spec: str,
    output_path: Path,
    fig_id: str,
    camera_fig_id: str | None = None,
    stride: int = 1,
    background: str = "white",
    axis_color: str = "black",
    show_colorbar: bool = True,
    show_lock_btn: bool = True,
    show_orientation: bool = True,
) -> None:
    """
    Generate a self-contained vtk.js HTML with multiple actors in one scene.

    ``sources`` is an ordered list of dicts, each with keys:
      src (Path), field (str), cmap (str), decimate (str), line_width (str)

    src1 (sources[0]) drives the time axis.  All other sources snap to their
    nearest timestep each frame.
    """
    import pyvista as pv
    from scripts.data_loader import SimulationData

    if not sources:
        raise ValueError("generate_multi_image_html requires at least one source")

    sims = [_get_simulation(s["src"]) for s in sources]
    sim1 = sims[0]
    field1 = sources[0]["field"]

    if sim1.n_steps == 0:
        raise RuntimeError(f"src1 at {sources[0]['src']} has no timesteps")

    n = sim1.n_steps
    idx = _resolve_time_index(time_spec, n)

    # ── Build initial frame ──────────────────────────────────────────────────
    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = background if background != "transparent" else "white"

    init_surfaces: list = []
    for si, (source, sim) in enumerate(zip(sources, sims)):
        field = source["field"]
        cmap = source.get("cmap") or _DEFAULT_CMAPS[si % len(_DEFAULT_CMAPS)]
        decimate = source.get("decimate", "auto")
        line_width = float(source.get("line_width", "2.0"))

        t_idx = idx if si == 0 else _nearest_time_idx(
            sim, sim1.time_steps[idx] if idx < len(sim1.time_steps) else 0.0
        )
        mesh = sim.get_mesh(t_idx)
        if mesh is None:
            print(f"Warning: src{si+1} has no mesh at step {t_idx}", file=sys.stderr)
            init_surfaces.append(None)
            continue

        surface = _prepare_surface(mesh)
        surface = _apply_decimation(surface, decimate, label=f"{fig_id}-src{si+1}")
        init_surfaces.append(surface)

        src_colorbar = show_colorbar and source.get("colorbar", si == 0)
        src_opacity = source.get("opacity", 1.0)
        sbar_args = _multi_image_scalar_bar_args(field, axis_color, si, src_colorbar)
        has_field = bool(field) and (field in surface.point_data or field in surface.cell_data)
        is_line = not _has_polygon_cells(surface)
        if field and not has_field:
            print(f"Warning: field '{field}' not found in src{si+1} — geometry only.", file=sys.stderr)

        mesh_kwargs: dict = dict(
            scalars=field if has_field else None,
            cmap=cmap,
            show_scalar_bar=src_colorbar and has_field,
            scalar_bar_args=sbar_args if has_field else {},
            opacity=src_opacity,
        )
        if not has_field:
            mesh_kwargs.update(color="#aaaaaa")
        if is_line:
            pl.add_mesh(surface, line_width=line_width, render_lines_as_tubes=True, **mesh_kwargs)
        else:
            pl.add_mesh(surface, smooth_shading=True, **mesh_kwargs)

    _cam_id = camera_fig_id or fig_id
    camera_path = _project_root / "state" / f"camera_{_cam_id}.json"
    apply_camera_state(pl, _cam_id or "unnamed", camera_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.export_html(str(output_path))
    pl.close()

    # ── Field data for src1 (field switcher at rest) ─────────────────────────
    src1_fields = sources[0].get("fields") or ([field1] if field1 else [])
    if isinstance(src1_fields, str):
        src1_fields = [f.strip() for f in src1_fields.split(",") if f.strip()]
    field_data_b64: dict[str, str] = {}
    field_ranges: dict[str, list[float]] = {}
    surf1 = init_surfaces[0] if init_surfaces else None
    if surf1 is not None:
        for f in src1_fields:
            arr_np = None
            if f in surf1.point_data:
                arr_np = surf1.point_data[f]
            elif f in surf1.cell_data:
                arr_np = surf1.cell_data_to_point_data().point_data.get(f)
            if arr_np is not None:
                arr_f32 = arr_np.astype("float32").ravel()
                field_data_b64[f] = _b64.b64encode(arr_f32.tobytes()).decode("ascii")
                field_ranges[f] = [float(arr_f32.min()), float(arr_f32.max())]

    # ── Time data (src1 primary + overlays) ──────────────────────────────────
    time_data_b64: dict[str, list[str]] = {}
    time_global_range: dict[str, list[float]] = {}
    time_labels: list[str] = []
    overlay_time_data_b64: dict[str, list[str]] = {}
    overlay_time_global_range: dict[str, list[float]] = {}
    overlay_field_names: list[str] = []

    for si in range(1, len(sources)):
        ov_f = sources[si]["field"]
        if ov_f:
            overlay_field_names.append(ov_f)
            overlay_time_data_b64[ov_f] = []
            overlay_time_global_range[ov_f] = [float("inf"), float("-inf")]

    if sim1.n_steps > 1 and src1_fields:
        step_indices = _timeline_step_indices(sim1, src1_fields, stride)
        primary_points = max(
            getattr(init_surfaces[0], "n_points", 0) if init_surfaces and init_surfaces[0] is not None else 0,
            getattr(init_surfaces[0], "n_cells", 0) if init_surfaces and init_surfaces[0] is not None else 0,
        )
        overlay_points = 0
        for surf in init_surfaces[1:]:
            if surf is None:
                continue
            overlay_points += max(getattr(surf, "n_points", 0), getattr(surf, "n_cells", 0))
        step_indices, capped_to = _apply_timeline_frame_budget(
            step_indices,
            point_budget=primary_points + overlay_points,
        )
        frame_idx = _frame_index_for_step(step_indices, idx)
        if capped_to is not None:
            print(
                f"{fig_id}: capped timeline to {len(step_indices)} frame(s)"
                f" for cold-render stability (requested stride={stride}).",
                file=sys.stderr,
            )
        print(
            f"{fig_id}: embedding {len(step_indices)} timesteps (stride={stride})"
            f" × {len(src1_fields)} primary field(s)"
            f" + {len(overlay_field_names)} overlay field(s) …",
            file=sys.stderr,
        )
        _tg_min = {f: float("inf") for f in src1_fields}
        _tg_max = {f: float("-inf") for f in src1_fields}
        for f in src1_fields:
            time_data_b64[f] = []
        decimate1 = sources[0].get("decimate", "auto")

        for t_idx in step_indices:
            time_labels.append(
                f"{sim1.time_steps[t_idx]:.4g}" if t_idx < len(sim1.time_steps) else str(t_idx)
            )

            # src1 frame
            t_mesh = sim1.get_mesh(t_idx)
            t_pts = None
            if t_mesh is not None:
                t_surface = _sample_on_reference(
                    init_surfaces[0] if init_surfaces and init_surfaces[0] else None,
                    t_mesh,
                )
                for f in src1_fields:
                    arr_np = None
                    if _mesh_has_field(t_mesh, f):
                        if f in t_surface.point_data:
                            arr_np = t_surface.point_data[f]
                        elif f in t_surface.cell_data:
                            if t_pts is None:
                                t_pts = t_surface.cell_data_to_point_data()
                            arr_np = t_pts.point_data.get(f)
                    if arr_np is not None:
                        arr_f32 = arr_np.astype("float32").ravel()
                        time_data_b64[f].append(_b64.b64encode(arr_f32.tobytes()).decode("ascii"))
                        _tg_min[f] = min(_tg_min[f], float(arr_f32.min()))
                        _tg_max[f] = max(_tg_max[f], float(arr_f32.max()))
                    else:
                        time_data_b64[f].append("")
            else:
                for f in src1_fields:
                    time_data_b64[f].append("")

            # overlay frames
            target_time = sim1.time_steps[t_idx] if t_idx < len(sim1.time_steps) else 0.0
            for si in range(1, len(sources)):
                ov_field = sources[si]["field"]
                if not ov_field:
                    continue
                ov_sim = sims[si]
                ov_t = _nearest_time_idx(ov_sim, target_time)
                ov_mesh = ov_sim.get_mesh(ov_t)
                arr_np = None
                if ov_mesh is not None:
                    ov_surf = _sample_on_reference(
                        init_surfaces[si] if init_surfaces and init_surfaces[si] else None,
                        ov_mesh,
                    )
                    if ov_field in ov_surf.point_data:
                        arr_np = ov_surf.point_data[ov_field]
                    elif ov_field in ov_surf.cell_data:
                        arr_np = ov_surf.cell_data_to_point_data().point_data.get(ov_field)
                if arr_np is not None:
                    arr_f32 = arr_np.astype("float32").ravel()
                    overlay_time_data_b64[ov_field].append(
                        _b64.b64encode(arr_f32.tobytes()).decode("ascii")
                    )
                    cur = overlay_time_global_range[ov_field]
                    overlay_time_global_range[ov_field] = [
                        min(cur[0], float(arr_f32.min())),
                        max(cur[1], float(arr_f32.max())),
                    ]
                else:
                    overlay_time_data_b64[ov_field].append("")

        for f in src1_fields:
            time_global_range[f] = (
                [_tg_min[f], _tg_max[f]] if _tg_min[f] != float("inf") else [0.0, 1.0]
            )

    # ── Patch HTML and inject controls + overlay extension ───────────────────
    html = output_path.read_text()
    html = html.replace("100vw", "900px").replace("100vh", "600px")

    if fig_id and "</body>" in html:
        try:
            step_list = step_indices
        except NameError:
            step_list = []
        try:
            control_time_idx = frame_idx
        except NameError:
            control_time_idx = 0
        inj = f"<script>var TIME_INDICES = {step_list};</script>\n" + _controls_strip_snippet(
            fig_id=fig_id,
            show_lock_btn=show_lock_btn,
            show_orientation=show_orientation,
            fields_to_embed=src1_fields,
            active_field=field1,
            field_data_b64=field_data_b64,
            field_ranges=field_ranges,
            time_labels=time_labels,
            time_data_b64=time_data_b64,
            time_global_range=time_global_range,
            time_idx=control_time_idx,
            time_field=field1,
        )
        inj += "\n" + _timeseries_sync_snippet(fig_id)
        if overlay_field_names:
            inj += "\n" + _multi_actor_extension_snippet(
                overlay_field_names,
                overlay_time_data_b64,
                overlay_time_global_range,
                fig_id=fig_id,
            )
        html = html.replace("</body>", inj + "\n</body>", 1)

    output_path.write_text(html, encoding="utf-8")
    _maybe_sign_output_html(output_path)
    print(f"Generated (multi-image): {output_path}", file=sys.stderr)

def generate_multi_image_png(
    sources: list[dict],
    time_spec: str,
    output_path: Path,
    fig_id: str,
    camera_fig_id: str | None = None,
    background: str = "white",
    axis_color: str = "black",
    show_colorbar: bool = True,
) -> None:
    """Generate a static PNG of a multi-source scene for PDF export."""
    import pyvista as pv
    from scripts.data_loader import SimulationData

    if not sources:
        raise ValueError("generate_multi_image_png requires at least one source")

    sims = [_get_simulation(s["src"]) for s in sources]
    sim1 = sims[0]

    n = sim1.n_steps
    if time_spec == "first":
        idx = 0
    elif time_spec == "last":
        idx = max(0, n - 1)
    else:
        try:
            idx = max(0, min(int(time_spec), n - 1))
        except ValueError:
            idx = n // 2

    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = background if background != "transparent" else "white"

    for si, (source, sim) in enumerate(zip(sources, sims)):
        field = source["field"]
        cmap = source.get("cmap") or _DEFAULT_CMAPS[si % len(_DEFAULT_CMAPS)]
        decimate = source.get("decimate", "auto")
        line_width = float(source.get("line_width", "2.0"))

        t_idx = idx if si == 0 else _nearest_time_idx(
            sim, sim1.time_steps[idx] if idx < len(sim1.time_steps) else 0.0
        )
        mesh = sim.get_mesh(t_idx)
        if mesh is None:
            continue

        surface = _prepare_surface(mesh)
        surface = _apply_decimation(surface, decimate, label=f"{fig_id}-src{si+1}.png")

        src_colorbar = show_colorbar and source.get("colorbar", si == 0)
        src_opacity = source.get("opacity", 1.0)
        sbar_args = _multi_image_scalar_bar_args(field, axis_color, si, src_colorbar)
        has_field = bool(field) and (field in surface.point_data or field in surface.cell_data)
        is_line = not _has_polygon_cells(surface)

        mesh_kwargs: dict = dict(
            scalars=field if has_field else None,
            cmap=cmap,
            show_scalar_bar=src_colorbar and has_field,
            scalar_bar_args=sbar_args if has_field else {},
            opacity=src_opacity,
        )
        if not has_field:
            mesh_kwargs.update(color="#aaaaaa")
        if is_line:
            pl.add_mesh(surface, line_width=line_width, render_lines_as_tubes=True, **mesh_kwargs)
        else:
            pl.add_mesh(surface, smooth_shading=True, **mesh_kwargs)

    _cam_id = camera_fig_id or fig_id
    camera_path = _project_root / "state" / f"camera_{_cam_id}.json"
    apply_camera_state(pl, _cam_id or "unnamed", camera_path)
    pl.add_axes(interactive=False, line_width=3)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pl.save_graphic(str(output_path.with_suffix(".pdf")))
    pl.screenshot(str(output_path))
    pl.close()
    print(f"Generated (multi-image PNG): {output_path}")

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

    sim = _get_simulation(src_path)

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

    surface = _prepare_surface(mesh)
    surface = _apply_decimation(surface, decimate, label=f"{fig_id or 'fig'}.png")

    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = background if background != "transparent" else "white"

    if field and field not in surface.point_data and field not in surface.cell_data:
        print(
            f"Warning: field '{field}' not found — rendering geometry only.",
            file=sys.stderr,
        )
    _add_mesh_auto(pl, surface, field=field, cmap=cmap,
                   show_colorbar=show_colorbar, axis_color=axis_color)

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
    broadcast_group: str = "",
) -> None:
    """
    Generate a self-contained vtk.js HTML figure using PyVista.

    Uses PyVista's Plotter.export_html() which produces a standalone
    file powered by panel + trame — no server required to view.
    """
    import pyvista as pv
    from scripts.data_loader import SimulationData

    sim = _get_simulation(src_path)

    if sim.n_steps == 0:
        raise RuntimeError(
            f"Simulation at {src_path} has no time steps. "
            "Ensure the case has been solved and time directories exist."
        )

    # Resolve time step index
    n = sim.n_steps
    idx = _resolve_time_index(time_spec, n)

    mesh = sim.get_mesh(idx)
    if mesh is None:
        raise RuntimeError(f"Could not load mesh at step {idx} from {src_path}")

    surface = _prepare_surface(mesh)
    surface = _apply_decimation(surface, decimate, label=f"{fig_id or 'fig'}.html")

    pl = pv.Plotter(off_screen=True, window_size=(900, 600))
    pl.background_color = background if background != "transparent" else "white"

    if field and field not in surface.point_data and field not in surface.cell_data:
        print(
            f"Warning: field '{field}' not found in mesh — rendering geometry only.",
            file=sys.stderr,
        )
    _add_mesh_auto(pl, surface, field=field, cmap=cmap,
                   show_colorbar=show_colorbar, axis_color=axis_color)

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
        step_indices = _timeline_step_indices(sim, fields_to_embed, stride)
        point_budget = max(getattr(surface, "n_points", 0), getattr(surface, "n_cells", 0))
        step_indices, capped_to = _apply_timeline_frame_budget(
            step_indices,
            point_budget=point_budget,
        )
        frame_idx = _frame_index_for_step(step_indices, idx)
        if capped_to is not None:
            print(
                f"{fig_id or 'fig'}: capped timeline to {len(step_indices)} frame(s)"
                f" for cold-render stability (requested stride={stride}).",
                file=sys.stderr,
            )
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
                
            # 2 & 3. Extract and Decimate (via direct sampling from volumetric mesh onto reference surface)
            ex_start = time.time()
            t_surface = _sample_on_reference(surface, t_mesh)
            ex_time = time.time() - ex_start
            
            dec_start = time.time()
            dec_time = time.time() - dec_start
            
            # 4. Process Arrays & Encode
            enc_start = time.time()
            t_pts = None  # lazily computed cell→point conversion, shared by all fields
            for f in fields_to_embed:
                arr_np = None
                if _mesh_has_field(t_mesh, f):
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
                try:
                    step_list = step_indices
                except NameError:
                    step_list = []
                inj_html = f"<script>var TIME_INDICES = {step_list};</script>\n" + _controls_strip_snippet(
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
                    time_idx=frame_idx if "frame_idx" in locals() else 0,
                    time_field=field,
                    broadcast_group=broadcast_group,
                ) + "\n" + _timeseries_sync_snippet(fig_id) + "\n</body>"
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
    frame_count = 0
    for sub in panel["subfigures"]:
        sub_path = figures_dir / f"{sub['id']}.html"
        frame_count = max(frame_count, _html_time_frame_count(sub_path))
        content = sub_path.read_text()
        b64 = _b64_panel.b64encode(content.encode()).decode("ascii")
        cells.append(
            f'<iframe src="data:text/html;base64,{b64}" '
            f'data-panel="{panel["id"]}" '
            f'style="width:100%;height:100%;border:none;" frameborder="0"></iframe>'
        )
    actual_indices = []
    if panel.get("timeseries"):
        if isinstance(panel.get("time_indices"), list):
            actual_indices = [int(v) for v in panel["time_indices"]]
        else:
            actual_indices = [int(sub.get("time", 0)) for sub in panel["subfigures"]]
    toolbar = _panel_transport_html(panel["id"], frame_count, actual_indices)

    composite = (
        f'<!DOCTYPE html><html><body style="margin:0;padding:0;">'
        f'{re_relay}'
        f'{toolbar}'
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
    if panel.get("timeseries"):
        manifest["time_indices"] = actual_indices
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

    sim = _get_simulation(src_path)
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
