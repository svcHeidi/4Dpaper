from __future__ import annotations
import sys
import math
import json
from pathlib import Path
import numpy as np
try:
    import pyvista as pv
except ImportError:
    pass

from .timeseries import _nearest_time_idx
from .config import _DECIMATE_TARGET_FACES

_PREPARE_CACHE = {}
_DECIMATE_CACHE = {}


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

def _surface_cell_count(surface) -> int:
    """Return a stable cell count across PyVista versions."""
    return int(getattr(surface, "n_cells", 0))

def _has_polygon_cells(surface) -> bool:
    """Return True if the mesh has any triangle/polygon cells (not just lines/points)."""
    try:
        return int(surface.GetNumberOfPolys()) > 0
    except Exception:
        return False

def _prepare_surface(mesh):
    """
    Return a renderable surface from any mesh type.

    For volumetric meshes (UnstructuredGrid, StructuredGrid, etc.) extract the
    boundary surface.  For PolyData the mesh is already a surface representation
    (including LINE-only Purkinje networks), so return it as-is — calling
    vtkDataSetSurfaceFilter on a LINES-only PolyData would strip line connectivity
    and return only the endpoint vertices.

    Detection order:
    1. VTK GetClassName() — works on real PyVista objects without an import.
    2. isinstance(mesh, pv.PolyData) — fallback for subclasses.
    3. extract_surface() — safe default for volumetric types and mocks.
    """
    if mesh is None:
        return None
        
    mesh_id = id(mesh)
    if mesh_id in _PREPARE_CACHE:
        return _PREPARE_CACHE[mesh_id]

    try:
        if mesh.GetClassName() == "vtkPolyData":
            return mesh
    except AttributeError:
        pass
    try:
        import pyvista as pv
        if isinstance(mesh, pv.PolyData):
            _PREPARE_CACHE[mesh_id] = mesh
            return mesh
    except (TypeError, ImportError):
        pass
        
    result = mesh.extract_surface(algorithm="dataset_surface")
    _PREPARE_CACHE[mesh_id] = result
    return result

def _add_mesh_auto(pl, surface, field: str, cmap: str, show_colorbar: bool,
                   axis_color: str, clim=None, line_width: float = 2.0):
    """
    Add a mesh to a Plotter, choosing rendering style based on cell type.

    Triangle/polygon meshes use smooth shading.  Line meshes (e.g. Purkinje
    networks) use render_lines_as_tubes so they are visible in the 3D view.
    """
    is_line = not _has_polygon_cells(surface)
    scalar_bar_args = {"title": field, "color": axis_color} if show_colorbar else {}
    has_field = bool(field) and (
        field in surface.point_data or field in surface.cell_data
    )
    common = dict(
        scalars=field if has_field else None,
        cmap=cmap,
        show_scalar_bar=show_colorbar and has_field,
        scalar_bar_args=scalar_bar_args if has_field else {},
    )
    if clim is not None:
        common["clim"] = clim
    if not has_field:
        common["color"] = "#aaaaaa"
        common["opacity"] = 0.9
    if is_line:
        pl.add_mesh(surface, line_width=line_width, render_lines_as_tubes=True, **common)
    else:
        pl.add_mesh(surface, smooth_shading=True, **common)

def _get_overlay_at_time(overlay_sim, target_time: float):
    """Return the overlay mesh whose simulation time is closest to target_time."""
    times = overlay_sim.time_steps
    if not times:
        return None
    nearest_idx = min(range(len(times)), key=lambda i: abs(times[i] - target_time))
    return overlay_sim.get_mesh(nearest_idx)

def _merge_overlay_mesh(primary, primary_field: str, overlay, overlay_field: str):
    """
    Merge a primary surface mesh with an overlay mesh under a single scalar field.

    The overlay's scalar (overlay_field) is copied into the merged mesh under
    primary_field so both datasets share one colormap.  All other point-data
    arrays are stripped to keep the merged mesh compact.

    Returns (merged_polydata, n_primary) where n_primary is the number of
    primary mesh points, which callers need to reconstruct per-frame arrays.
    """
    import pyvista as pv
    import numpy as np

    n_primary = primary.n_points

    # Build a clean primary PolyData with only the unified field
    prim = pv.PolyData(primary.points, primary.cells)
    if primary_field in primary.point_data:
        prim.point_data[primary_field] = primary.point_data[primary_field].astype("float32")
    elif primary_field in primary.cell_data:
        tmp = primary.cell_data_to_point_data()
        if primary_field in tmp.point_data:
            prim.point_data[primary_field] = tmp.point_data[primary_field].astype("float32")

    # Build a clean overlay PolyData with the overlay field renamed to primary_field
    over = pv.PolyData(overlay.points, overlay.lines)
    if overlay_field in overlay.point_data:
        over.point_data[primary_field] = overlay.point_data[overlay_field].astype("float32")

    merged = prim.merge(over)
    return merged, n_primary

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
    if surface is None:
        return None

    spec = (decimate_spec or "auto").strip().lower()
    if spec in ("0", "none", "off", "false", "no"):
        return surface

    cache_key = (id(surface), spec)
    if cache_key in _DECIMATE_CACHE:
        return _DECIMATE_CACHE[cache_key]

    # Line/point meshes (e.g. Purkinje networks) have no polygon cells — skip.
    if not _has_polygon_cells(surface):
        print(
            f"{label}: skipping decimation — no polygon cells (line/point mesh)",
            file=sys.stderr,
        )
        return surface

    # Attempt to load from disk cache
    cache_file = None
    try:
        from .config import _project_root
        import hashlib
        import numpy as np

        h = hashlib.md5()
        h.update(spec.encode("utf-8"))
        h.update(str(getattr(surface, "n_points", 0)).encode("utf-8"))
        h.update(str(getattr(surface, "n_cells", 0)).encode("utf-8"))

        if hasattr(surface, "points") and surface.points is not None:
            h.update(np.ascontiguousarray(surface.points).data)
        
        # Include scalar fields in hash, since decimation interpolates them
        if hasattr(surface, "point_data"):
            for name in sorted(surface.point_data.keys()):
                h.update(name.encode("utf-8"))
                arr = surface.point_data[name]
                if arr is not None:
                    h.update(np.ascontiguousarray(arr).data)
        if hasattr(surface, "cell_data"):
            for name in sorted(surface.cell_data.keys()):
                h.update(name.encode("utf-8"))
                arr = surface.cell_data[name]
                if arr is not None:
                    h.update(np.ascontiguousarray(arr).data)

        mesh_hash = h.hexdigest()
        cache_dir = _project_root / ".cache" / "decimation"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{mesh_hash}.vtk"

        if cache_file.exists():
            import pyvista as pv
            result = pv.read(cache_file)
            _DECIMATE_CACHE[cache_key] = result
            return result
    except Exception as e:
        pass

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
        
    if cache_file is not None:
        try:
            result.save(cache_file)
        except Exception:
            pass

    _DECIMATE_CACHE[cache_key] = result
    return result

