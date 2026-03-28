# Multi-Format 3D Loader Extension

**Date:** 2026-03-19
**File:** `scripts/data_loader.py`
**Status:** Approved

## Goal

Extend `SimulationData` to load all common 3D simulation/mesh file formats beyond OpenFOAM, with each format as a standalone public method callable independently of auto-detection.

## Approach: Public loader methods + auto-dispatch (Option B)

Each format gets a `load_<format>(self)` public method. `load()` auto-detects the format and dispatches. Callers can also invoke `sim.load_ensight()` directly, bypassing detection.

## Bug fix: `_meshes` cache key inconsistency

**Problem:** `_load_vtk_single` and `_load_vtk_directory` currently store with bare `int` keys (`{0: mesh}`). `get_mesh()` looks up `(step_index, part)` tuples, so it always misses the cache and falls through to `self._reader` (which is `None` for VTK single/directory) → returns `None`. All new loaders would have the same problem.

**Fix (write side):** Change `_load_vtk_single` and `_load_vtk_directory` to write `(i, "default")` keys. All new `load_<format>()` methods also write `(step_index, "default")`.

**Fix (read side in `get_mesh()`):** After the `(step_index, part)` lookup fails, add a fallback to `(step_index, "default")`:

```python
default_key = (step_index, "default")
if default_key in self._meshes:
    return self._meshes[default_key]
```

This also fixes `__iter__`, which calls `get_mesh(i)` with the default `part="internalMesh"` and would otherwise miss all non-OpenFOAM cached meshes.

## Bug fix: `EnableAllCellArrays` in `get_mesh()`

`get_mesh()` currently calls `self._reader._reader.EnableAllCellArrays()` and `EnableAllPointArrays()` unconditionally before reading. This is OpenFOAM-specific and will raise `AttributeError` on CGNS, Exodus, XDMF, and EnSight readers.

**Fix:** Guard that block to OpenFOAM formats only. `PVDReader` also sets `self._reader`, but its underlying VTK reader (`vtkXMLGenericDataObjectReader`) does not expose `EnableAllCellArrays` — so `pvd` must be excluded from the guard:

```python
if self._format in ("openfoam", "openfoam_decomposed"):
    vtk_r = self._reader._reader
    vtk_r.EnableAllCellArrays()
    vtk_r.EnableAllPointArrays()
```

## Formats

| Group | Extensions | Method | Backend |
|---|---|---|---|
| VTK family | `.vtp` | `load_vtp()` | `pv.read()` |
| Surface meshes | `.stl` | `load_stl()` | `pv.read()` |
| Surface meshes | `.obj` | `load_obj()` | `pv.read()` |
| Surface meshes | `.ply` | `load_ply()` | `pv.read()` |
| CFD time-series | `.case` | `load_ensight()` | `pv.EnSightReader()` (direct instantiation) |
| CFD time-series | `.cgns` | `load_cgns()` | `pv.CGNSReader()` |
| FEA time-series | `.exo`, `.e`, `.ex2` | `load_exodus()` | `pv.ExodusIIReader()` |
| XDMF+HDF5 | `.xdmf`, `.xmf` | `load_xdmf()` | `pv.XdmfReader()` (note: lower-case 'd') |
| meshio-backed | `.hdf5` | `load_hdf5()` | lazy `meshio` |
| meshio-backed | `.med` | `load_med()` | lazy `meshio` |
| meshio-backed | `.msh` | `load_msh()` | lazy `meshio` |

**Note on `.h5`:** PyVista's built-in reader maps `.h5` to `FLUENTCFFReader`. To avoid silently misrouting FLUENT `.h5` files through meshio, `.h5` is **not** added to `SUFFIX_MAP`. Only `.hdf5` is mapped to the meshio path. Users with FLUENT `.h5` files should use PyVista's `pv.FluentCFFReader` directly.

**Note on `.xdmf` + companion files:** `meshio.read()` and `pv.XdmfReader()` both resolve companion `.h5` files relative to the `.xdmf` file path. The companion file must be in the same directory as the `.xdmf` file.

## Architecture

### `_detect_format()`

The suffix-to-format mapping is expressed as a flat dict `SUFFIX_MAP`. The insertion order within `_detect_format()` is:

1. Existing: check `.foam` / `.openfoam` first (may detect decomposed)
2. **New:** look up suffix in `SUFFIX_MAP` (covers all new formats + existing `.pvd`, `.vtu`, `.vtk`)
3. Existing: directory fallback (`vtk_directory`)
4. Existing: raise `ValueError` with full list of supported extensions

The `.e` short extension is included in `SUFFIX_MAP` for Exodus. It is kept because Exodus files with `.e` are well-established in the FEA world (Sandia/Sierra toolchain). The risk of collision with non-3D files is low in a scientific context.

```python
SUFFIX_MAP = {
    # VTK family
    ".pvd": "pvd", ".vtu": "vtk_single", ".vtk": "vtk_single", ".vtp": "vtp",
    # Surface meshes
    ".stl": "stl", ".obj": "obj", ".ply": "ply",
    # CFD
    ".case": "ensight", ".cgns": "cgns",
    # FEA
    ".exo": "exodus", ".e": "exodus", ".ex2": "exodus",
    # XDMF
    ".xdmf": "xdmf", ".xmf": "xdmf",
    # meshio-backed (note: .h5 excluded — conflicts with FLUENT CFF)
    ".hdf5": "hdf5", ".med": "med", ".msh": "msh",
}
```

### `load()` dispatch

```python
LOADERS = {
    "openfoam": self.load_openfoam,
    "openfoam_decomposed": self.load_openfoam_decomposed,
    "pvd": self.load_pvd,
    "vtk_single": self.load_vtk_single,
    "vtk_directory": self.load_vtk_directory,
    "vtp": self.load_vtp,
    "stl": self.load_stl,
    "obj": self.load_obj,
    "ply": self.load_ply,
    "ensight": self.load_ensight,
    "cgns": self.load_cgns,
    "exodus": self.load_exodus,
    "xdmf": self.load_xdmf,
    "hdf5": self.load_hdf5,
    "med": self.load_med,
    "msh": self.load_msh,
}
LOADERS[self._format]()
```

### Reader-based loaders (EnSight, CGNS, Exodus, XDMF)

All follow the same pattern, using direct class instantiation (not `pv.get_reader()`):

```python
def load_ensight(self):
    reader = pv.EnSightReader(str(self.case_path))
    self._time_steps = list(reader.time_values) or [0]
    self._reader = reader
    self._format = "ensight"
```

`get_mesh()` handles `self._reader` via `set_active_time_point` + `read()`. MultiBlock output is combined when no matching part name is found (existing behaviour). The `EnableAllCellArrays` block is now guarded (see bug fix above), so these readers are safe.

CGNS additionally enables all bases and families:

```python
def load_cgns(self):
    reader = pv.CGNSReader(str(self.case_path))
    reader.enable_all_bases()
    reader.enable_all_families()
    self._time_steps = list(reader.time_values) or [0]
    self._reader = reader
    self._format = "cgns"
```

### Single-mesh loaders (VTP, STL, OBJ, PLY)

```python
def load_stl(self):
    """Load an STL surface mesh (one time step)."""
    self._time_steps = [0]
    self._meshes[(0, "default")] = pv.read(str(self.case_path))
    self._format = "stl"
```

Same pattern for `load_vtp()`, `load_obj()`, `load_ply()`.

### meshio-backed loaders (HDF5, MED, MSH)

Shared private helper:

```python
def _read_via_meshio(self) -> pv.DataSet:
    try:
        import meshio
    except ImportError:
        raise ImportError(
            "meshio is required for this format. "
            "Install with: pip install meshio"
        )
    return pv.from_meshio(meshio.read(str(self.case_path)))
```

Each public method:

```python
def load_hdf5(self):
    """Load a generic HDF5 mesh via meshio (requires meshio + h5py)."""
    self._time_steps = [0]
    self._meshes[(0, "default")] = self._read_via_meshio()
    self._format = "hdf5"
```

Same pattern for `load_med()` and `load_msh()`.

## Error handling

- Unsupported format: `ValueError` in `_detect_format()` listing all supported extensions
- Missing meshio: `ImportError` with install hint, raised at call time (lazy)
- CGNS/Exodus/XDMF/EnSight: no special handling beyond what PyVista provides

## What is NOT changing

- `SimulationData.__init__` signature
- OpenFOAM reconstructed and decomposed loading logic (`load_openfoam`, `load_openfoam_decomposed`, `_get_decomposed_mesh`)
- `fields`, `time_steps`, `n_steps`, `summary`, `cleanup`, `__iter__`, `__len__`
