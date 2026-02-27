"""
interactive_viz.py — 3D Visualization Engineer Module

Creates interactive PyVista visualizations with time-step sliders,
scalar field toggles, and Trame-based web rendering for Quarto embedding.

Corresponds to: agents.yaml → visualization_engineer
Corresponds to: tasks.yaml  → viz_logic_task
"""

import pyvista as pv
import numpy as np


def create_interactive_plot(
    sim_data,
    scalar_field: str = "U",
    cmap: str = "coolwarm",
    clim: tuple = None,
    window_size: tuple = (900, 600),
):
    """
    Create an interactive 3D plot with time-step slider and scalar overlay.
    
    This function is designed to work inside a Quarto .qmd code cell
    using PyVista's Trame backend for browser rendering.
    
    Args:
        sim_data: A loaded SimulationData instance.
        scalar_field: Name of the scalar/vector field to visualize (e.g., "U", "p").
        cmap: Matplotlib colormap name.
        clim: Optional (min, max) tuple for scalar color limits.
        window_size: Render window dimensions.
    
    Returns:
        The PyVista Plotter (for Quarto/Jupyter to display).
    """
    # Configure PyVista for Quarto/Jupyter rendering
    pv.set_jupyter_backend("trame")
    pv.global_theme.anti_aliasing = "ssaa"
    pv.global_theme.background = "#1a1a2e"
    pv.global_theme.font.color = "#e0e0e0"

    # Get the initial mesh
    initial_mesh = sim_data.get_mesh(0)

    # Compute scalar magnitude if vector field
    active_scalars = _resolve_scalar(initial_mesh, scalar_field)

    # Auto-compute color limits across all time steps if not provided
    if clim is None:
        clim = _compute_global_clim(sim_data, scalar_field)

    # Create the plotter
    pl = pv.Plotter(window_size=window_size)
    
    # Add the mesh actor
    actor = pl.add_mesh(
        initial_mesh,
        scalars=active_scalars,
        cmap=cmap,
        clim=clim,
        show_edges=False,
        lighting=True,
        smooth_shading=True,
        scalar_bar_args={
            "title": scalar_field,
            "title_font_size": 14,
            "label_font_size": 12,
            "shadow": True,
            "fmt": "%.2f",
            "position_x": 0.05,
            "position_y": 0.05,
        },
    )

    # Add time-step slider
    def _update_time(value):
        step = int(round(value))
        mesh = sim_data.get_mesh(step)
        if mesh is not None:
            resolved = _resolve_scalar(mesh, scalar_field)
            actor.mapper.dataset.copy_from(mesh)

    if sim_data.n_steps > 1:
        pl.add_slider_widget(
            _update_time,
            rng=[0, sim_data.n_steps - 1],
            value=0,
            title="Time Step",
            pointa=(0.25, 0.92),
            pointb=(0.75, 0.92),
            style="modern",
        )

    # Camera and lighting
    pl.add_light(pv.Light(position=(5, 5, 10), intensity=0.7))
    pl.camera_position = "xy"
    pl.enable_anti_aliasing("ssaa")

    return pl


def _resolve_scalar(mesh, field_name: str):
    """
    Resolve a scalar field name — if it's a vector field (3-component),
    compute its magnitude and add it as a new scalar array.
    """
    if field_name in mesh.point_data:
        data = mesh.point_data[field_name]
    elif field_name in mesh.cell_data:
        data = mesh.cell_data[field_name]
    else:
        return None

    if data.ndim > 1 and data.shape[1] == 3:
        mag_name = f"{field_name}_magnitude"
        mesh[mag_name] = np.linalg.norm(data, axis=1)
        return mag_name

    return field_name


def _compute_global_clim(sim_data, field_name: str):
    """Compute global min/max across all time steps for consistent coloring."""
    global_min = float("inf")
    global_max = float("-inf")

    for _, mesh in sim_data:
        if mesh is None:
            continue
        resolved = _resolve_scalar(mesh, field_name)
        if resolved and resolved in mesh.point_data:
            arr = mesh.point_data[resolved]
        elif resolved and resolved in mesh.cell_data:
            arr = mesh.cell_data[resolved]
        else:
            continue
        global_min = min(global_min, float(np.min(arr)))
        global_max = max(global_max, float(np.max(arr)))

    if global_min == float("inf"):
        return (0, 1)
    return (global_min, global_max)
