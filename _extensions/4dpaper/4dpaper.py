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
sys.path.insert(0, str(_here.parent))
from lib.config import _project_root, _app_root, ShortcutResolver, _shortcut_resolver, _shortcuts_yml_path

for _path in (_app_root, _project_root):
    if _path is not None and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from lib.utils import resolve_src_path, is_cache_valid, _maybe_sign_output_html
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



from dashboard.document_signing import sign_html_file_if_configured
sys.path.insert(0, str(_here.parent))
from lib.parser import parse_graph_shortcodes, parse_panel_shortcodes, parse_shortcodes, parse_video_shortcodes, parse_multi_image_shortcodes, parse_timeseries_shortcodes
from lib.mesh import _rdp_simplify_xy, _get_overlay_at_time, _prepare_surface, _decimate_quadric, _surface_cell_count, _decimate_surface, _has_polygon_cells, _add_mesh_auto, _apply_decimation, _merge_overlay_mesh
from lib.utils import is_cache_valid, resolve_src_path, _maybe_sign_output_html
from lib.render import generate_multi_image_png, generate_png_figure, generate_panel_html, generate_multi_image_html, generate_panel_png, generate_video_figure, generate_html_figure
from lib.frontend import _controls_strip_snippet, _build_video_html_fragment, _build_timeseries_composite_html, _multi_actor_extension_snippet, _generate_optimized_timeseries_html, _build_multi_image_sources, _timeseries_sync_snippet, _plotly_camera_sync_snippet
from lib.state import _apply_camera_from_dict, apply_camera_state, load_styles, _load_saved_field_state, resolve_style
from lib.timeseries import _expand_timeseries_steps, _check_same_mesh_timeseries, _nearest_time_idx































































_DEFAULT_CMAPS = ["coolwarm", "plasma", "viridis", "RdBu"]

_COLORBAR_POSITIONS = [
    {"position_x": 0.02, "position_y": 0.05, "width": 0.22, "height": 0.10},
    {"position_x": 0.76, "position_y": 0.05, "width": 0.22, "height": 0.10},
    {"position_x": 0.76, "position_y": 0.20, "width": 0.22, "height": 0.10},
    {"position_x": 0.76, "position_y": 0.35, "width": 0.22, "height": 0.10},
]

_PLOTLY_3D_TRACE_TYPES = {
    "scatter3d",
    "surface",
    "mesh3d",
    "cone",
    "streamtube",
    "volume",
    "isosurface",
}


def _plotly_scene_keys(fig) -> list[str]:
    layout = fig.to_plotly_json().get("layout", {})
    keys = [k for k in layout if re.fullmatch(r"scene\d*", k)]
    if keys:
        return keys
    trace_types = {
        getattr(trace, "type", "")
        for trace in getattr(fig, "data", [])
    }
    return ["scene"] if any(t in _PLOTLY_3D_TRACE_TYPES for t in trace_types) else []


def _plotly_camera_from_saved_state(camera_data: dict | None) -> dict | None:
    if not isinstance(camera_data, dict):
        return None
    position = camera_data.get("position")
    focal_point = camera_data.get("focal_point") or [0.0, 0.0, 0.0]
    view_up = camera_data.get("view_up")
    if not (isinstance(position, list) and len(position) >= 3):
        return None
    if not (isinstance(view_up, list) and len(view_up) >= 3):
        return None
    if not (isinstance(focal_point, list) and len(focal_point) >= 3):
        focal_point = [0.0, 0.0, 0.0]
    return {
        "eye": {
            "x": float(position[0]),
            "y": float(position[1]),
            "z": float(position[2]),
        },
        "center": {
            "x": float(focal_point[0]),
            "y": float(focal_point[1]),
            "z": float(focal_point[2]),
        },
        "up": {
            "x": float(view_up[0]),
            "y": float(view_up[1]),
            "z": float(view_up[2]),
        },
        "projection": {
            "type": "orthographic"
            if camera_data.get("parallel_projection", 0) == 1
            else "perspective"
        },
    }


def _apply_saved_plotly_camera(fig, fig_id: str) -> bool:
    camera_path = _project_root / "state" / f"camera_{fig_id}.json"
    if not camera_path.exists():
        return False
    try:
        camera_data = json.loads(camera_path.read_text())
    except Exception as exc:
        print(f"Warning: could not read camera for {fig_id}: {exc}", file=sys.stderr)
        return False

    plotly_camera = _plotly_camera_from_saved_state(camera_data)
    if plotly_camera is None:
        return False

    scene_keys = _plotly_scene_keys(fig)
    if not scene_keys:
        return False

    fig.update_layout({
        scene_key: {"camera": plotly_camera}
        for scene_key in scene_keys
    })
    print(
        f"Applied saved Plotly camera for {fig_id} to {', '.join(scene_keys)}",
        file=sys.stderr,
    )
    return True

























# ── Video figure generation ───────────────────────────────────────────────────





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
    multi_images = []
    for qmd in qmd_files:
        text = qmd.read_text()
        figures.extend(parse_shortcodes(text))
        videos.extend(parse_video_shortcodes(text))
        panels.extend(parse_panel_shortcodes(text))
        ts_raw.extend(parse_timeseries_shortcodes(text))
        multi_images.extend(parse_multi_image_shortcodes(text))
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
    
    if _here.exists():
        figure_extra_deps.append(_here)
    figure_extra_deps.extend(_here.parent.glob("lib/*.py"))

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
            ts["time_indices"] = step_indices
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

        # Check if all frame HTMLs and PNGs exist
        frame_ids = [f"{ts_id}-frame-{i}" for i in range(len(ts["step_indices"]))]
        frame_htmls = [figures_dir / f"{fid}.html" for fid in frame_ids]
        frame_pngs = [figures_dir / f"{fid}.png" for fid in frame_ids]
        all_frames_exist = all(fp.exists() for fp in frame_htmls) and all(fp.exists() for fp in frame_pngs)

        # Cache check — also verify all frames exist
        if all_frames_exist and is_cache_valid(output_path, ts["src_path"], extra_deps=figure_extra_deps):
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
                "time_indices": ts["step_indices"],
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

        camera_path = _project_root / "state" / f"camera_{fig_id}.json"
        
        # Always generate both .html (for web) and .png (for PDF).
        # QUARTO_OUTPUT_FORMAT is not reliably set for project pre-render hooks,
        # so we keep both formats up to date on every render pass.
        out_html = figures_dir / f"{fig_id}.html"
        
        if is_cache_valid(out_html, src, camera_path=camera_path, field_path=field_state_path, extra_deps=figure_extra_deps):
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

        mp4_valid = is_cache_valid(mp4_path, src, camera_path=camera_path, extra_deps=figure_extra_deps)
        frame_valid = is_cache_valid(frame_path, src, camera_path=camera_path, extra_deps=figure_extra_deps)
        html_valid = is_cache_valid(video_html_path, src, camera_path=camera_path, extra_deps=figure_extra_deps)

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
        for dep in figure_extra_deps:
            if dep.exists():
                sub_mtimes.append(dep.stat().st_mtime)
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
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"
        
        cache_ok = (
            is_cache_valid(out_html, src, camera_path=camera_path, extra_deps=figure_extra_deps)
            and is_cache_valid(out_png, src, camera_path=camera_path, extra_deps=figure_extra_deps)
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
            graph_has_saved_camera = _apply_saved_plotly_camera(fig, fig_id)
            
            # Re-theme the figure background so it matches the surrounding page neatly
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

            # Export PNG for static PDF builds. Plotly auto-selects Kaleido when installed.
            pio.write_image(fig, out_png, format="png", scale=2)

            # Export standalone HTML for interactive web
            html_content = pio.to_html(fig, full_html=True, include_plotlyjs="cdn", config={'displayModeBar': False})
            
            # Plotly figures need their own camera relay because there is no vtk.js controls strip.
            inj_html = _plotly_camera_sync_snippet(fig_id)
            if graph_has_saved_camera:
                print(f"Graph camera for {fig_id}: using saved camera for HTML/PDF export", file=sys.stderr)
            elif camera_path.exists():
                print(f"Graph camera for {fig_id}: saved file found but no 3D scene consumed it", file=sys.stderr)
            else:
                print(f"Graph camera for {fig_id}: not set", file=sys.stderr)
            if '</body>' in html_content:
                html_content = html_content.replace('</body>', inj_html + '\n</body>', 1)
            else:
                html_content += inj_html
                
            out_html.write_text(html_content, encoding="utf-8")
            _maybe_sign_output_html(out_html)
        except Exception as exc:
            print(f"ERROR generating Graph figure {fig_id}: {exc}", file=sys.stderr)
            sys.exit(1)


    # ── 4d-multi-image shortcode processing ───────────────────────────────────
    for fig in multi_images:
        fig_id = fig["id"]
        sources = _build_multi_image_sources(fig, resolve_src_path)
        if not sources:
            print(f"WARNING: 4d-multi-image '{fig_id}' has no valid src attributes — skipping.", file=sys.stderr)
            continue
        multi_style = resolve_style(styles_config, fig.get("style", ""), sources[0].get("field", ""))

        time_spec = fig.get("time", "mid")
        _, time_spec = _load_saved_field_state(fig_id, "", time_spec)
        stride = int(fig.get("stride", "1"))

        out_html = figures_dir / f"{fig_id}.html"
        out_png = figures_dir / f"{fig_id}.png"
        camera_path = _project_root / "state" / f"camera_{fig_id}.json"

        # Cache: invalidate if any source changes
        src1 = sources[0]["src"]
        extra_srcs = [s["src"] for s in sources[1:] if s["src"].exists()]
        
        html_fresh = is_cache_valid(out_html, src1, camera_path=camera_path, extra_deps=extra_srcs + figure_extra_deps)
        
        if html_fresh:
            print(f"{fig_id}.html is up to date — skipping.", file=sys.stderr)
        else:
            print(f"Generating {fig_id}.html (multi-image, {len(sources)} sources) …", file=sys.stderr)
            try:
                generate_multi_image_html(
                    sources, time_spec, out_html, fig_id,
                    stride=stride,
                    background=multi_style["background"],
                    axis_color=multi_style["axis_color"],
                )
            except Exception as exc:
                print(f"ERROR generating {fig_id}.html: {exc}", file=sys.stderr)
                sys.exit(1)

        png_fresh = is_cache_valid(out_png, src1, camera_path=camera_path, extra_deps=extra_srcs + figure_extra_deps)
        if png_fresh:
            print(f"{fig_id}.png is up to date — skipping.")
        else:
            print(f"Generating {fig_id}.png …")
            try:
                generate_multi_image_png(
                    sources, time_spec, out_png, fig_id,
                    background=multi_style["background"],
                    axis_color=multi_style["axis_color"],
                )
            except Exception as exc:
                if strict_static_export:
                    print(f"ERROR: could not generate {fig_id}.png: {exc}")
                    sys.exit(1)
                print(f"WARNING: could not generate {fig_id}.png: {exc}")


if __name__ == "__main__":
    main()
