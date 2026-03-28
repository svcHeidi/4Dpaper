# Multi-Format 3D Loader Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `SimulationData` in `scripts/data_loader.py` to support 11 new 3D file formats, each as a standalone public method, while fixing two latent bugs.

**Architecture:** Each format gets a public `load_<format>(self)` method. `_detect_format()` dispatches via a `SUFFIX_MAP` dict. `get_mesh()` gains a `"default"` key fallback so non-OpenFOAM formats hit the cache correctly. Meshio-backed formats use a shared `_read_via_meshio()` helper with a lazy import.

**Tech Stack:** PyVista (pv.read, pv.EnSightReader, pv.CGNSReader, pv.ExodusIIReader, pv.XdmfReader), meshio (lazy import for .hdf5/.med/.msh), pytest, unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-19-multi-format-loaders-design.md`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `tests/test_data_loader.py` | All tests for data_loader |
| Modify | `scripts/data_loader.py` | Bug fixes + new loaders |

---

### Task 1: Test file skeleton + cache key bug fix (write side)

The existing `_load_vtk_single` and `_load_vtk_directory` store meshes with bare `int` keys (`{0: mesh}`). `get_mesh()` looks up `(step_index, part)` tuples so it always misses the cache. Fix: write with `(i, "default")` keys.

**Files:**
- Create: `tests/test_data_loader.py`
- Modify: `scripts/data_loader.py:174-177` (`_load_vtk_single`, `_load_vtk_directory`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_loader.py
"""Tests for scripts/data_loader.py"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from data_loader import SimulationData


class TestCacheKeyBugFix:
    """Existing VTK single/directory loaders stored bare int keys; get_mesh expects tuples."""

    def test_vtk_single_cache_key_is_tuple(self, tmp_path):
        """load_vtk_single must store mesh under (0, 'default'), not bare 0."""
        fake_mesh = MagicMock()
        p = tmp_path / "mesh.vtu"
        p.touch()
        sim = SimulationData.__new__(SimulationData)
        sim.case_path = p
        sim._meshes = {}
        sim._time_steps = []
        sim._reader = None
        sim._format = "vtk_single"
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        with patch("data_loader.pv.read", return_value=fake_mesh):
            sim.load_vtk_single()
        assert (0, "default") in sim._meshes
        assert 0 not in sim._meshes  # bare int key must be gone

    def test_vtk_directory_cache_keys_are_tuples(self, tmp_path):
        """load_vtk_directory must store each mesh under (i, 'default')."""
        fake_mesh = MagicMock()
        for name in ["a.vtu", "b.vtu"]:
            (tmp_path / name).touch()
        sim = SimulationData.__new__(SimulationData)
        sim.case_path = tmp_path
        sim._meshes = {}
        sim._time_steps = []
        sim._reader = None
        sim._format = "vtk_directory"
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        with patch("data_loader.pv.read", return_value=fake_mesh):
            sim.load_vtk_directory()
        assert (0, "default") in sim._meshes
        assert (1, "default") in sim._meshes
        assert 0 not in sim._meshes
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/simaocastro/4Dpapers
pytest tests/test_data_loader.py::TestCacheKeyBugFix -v
```

Expected: FAIL — `AssertionError` because current code uses bare int keys.

- [ ] **Step 3: Fix `_load_vtk_single` and `_load_vtk_directory` in `data_loader.py`**

Replace `_load_vtk_single` (around line 174):

```python
def load_vtk_single(self):
    """Load a single VTK/VTU/VTP file (one time step)."""
    self._time_steps = [0]
    self._meshes[(0, "default")] = pv.read(str(self.case_path))
    self._format = "vtk_single"
```

Replace `_load_vtk_directory` (around line 166):

```python
def load_vtk_directory(self):
    """Load a directory of .vtu files, treating each file as one time step."""
    vtu_files = sorted(glob.glob(str(self.case_path / "*.vtu")))
    self._time_steps = list(range(len(vtu_files)))
    for i, f in enumerate(vtu_files):
        self._meshes[(i, "default")] = pv.read(f)
    self._format = "vtk_directory"
```

Also rename `_load_pvd` → `load_pvd` (make public, set `self._format`):

```python
def load_pvd(self):
    """Load a PVD XML collection that indexes multiple VTK files with timestamps."""
    reader = pv.PVDReader(str(self.case_path))
    self._time_steps = list(reader.time_values) or [0]
    self._reader = reader
    self._format = "pvd"
```

**Also update the `load()` method's existing `elif` branches** to call the renamed public names (Task 8 will fully rewrite `load()` with a dispatch dict, but `load()` must not break in the meantime):

```python
# In load(), update these three elif branches:
elif self._format == "pvd":
    self.load_pvd()            # was self._load_pvd()
elif self._format == "vtk_directory":
    self.load_vtk_directory()  # was self._load_vtk_directory()
elif self._format == "vtk_single":
    self.load_vtk_single()     # was self._load_vtk_single()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_data_loader.py::TestCacheKeyBugFix -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_data_loader.py scripts/data_loader.py
git commit -m "fix: vtk single/directory loaders now store meshes with (i, 'default') tuple keys"
```

---

### Task 2: Fix `get_mesh()` read-side fallback

`get_mesh(step, part="internalMesh")` never finds `(step, "default")` entries. Add a fallback lookup so all non-OpenFOAM cached meshes are returned correctly.

**Files:**
- Modify: `scripts/data_loader.py` (`get_mesh`)
- Modify: `tests/test_data_loader.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loader.py`:

```python
class TestGetMeshFallback:
    """get_mesh must fall back to (step, 'default') when exact part key is absent."""

    def _make_sim(self, mesh):
        sim = SimulationData.__new__(SimulationData)
        sim._meshes = {(0, "default"): mesh}
        sim._time_steps = [0]
        sim._reader = None
        sim._format = "stl"
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        return sim

    def test_get_mesh_returns_default_when_part_not_found(self):
        """Calling get_mesh(0) with default part='internalMesh' must return the cached mesh."""
        fake_mesh = MagicMock()
        sim = self._make_sim(fake_mesh)
        result = sim.get_mesh(0)  # part defaults to "internalMesh"
        assert result is fake_mesh

    def test_get_mesh_exact_key_takes_priority(self):
        """When the exact (step, part) key exists, it takes priority over default."""
        openfoam_mesh = MagicMock()
        default_mesh = MagicMock()
        sim = SimulationData.__new__(SimulationData)
        sim._meshes = {
            (0, "internalMesh"): openfoam_mesh,
            (0, "default"): default_mesh,
        }
        sim._time_steps = [0]
        sim._reader = None
        sim._format = "openfoam"
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        result = sim.get_mesh(0, part="internalMesh")
        assert result is openfoam_mesh
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_data_loader.py::TestGetMeshFallback -v
```

Expected: FAIL — `test_get_mesh_returns_default_when_part_not_found` returns `None`.

- [ ] **Step 3: Add fallback lookup in `get_mesh()`**

In `data_loader.py`, inside `get_mesh()`, after the `if mesh_key in self._meshes` block, add:

```python
# Non-OpenFOAM formats store under "default" — fall back when part not found
default_key = (step_index, "default")
if default_key in self._meshes:
    return self._meshes[default_key]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_data_loader.py::TestGetMeshFallback -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/data_loader.py tests/test_data_loader.py
git commit -m "fix: get_mesh now falls back to (step, 'default') for non-OpenFOAM formats"
```

---

### Task 3: Fix `EnableAllCellArrays` guard in `get_mesh()`

Currently called unconditionally on every reader. Only `OpenFOAMReader` has this method; calling it on CGNS/Exodus/XDMF/EnSight/PVD readers will raise `AttributeError`.

**Files:**
- Modify: `scripts/data_loader.py` (`get_mesh`)
- Modify: `tests/test_data_loader.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loader.py`:

```python
class TestEnableAllArraysGuard:
    """EnableAllCellArrays must only be called for openfoam formats."""

    def _make_reader_sim(self, fmt):
        fake_reader = MagicMock()
        # Make _reader NOT have EnableAllCellArrays to simulate non-OpenFOAM reader
        del fake_reader._reader.EnableAllCellArrays
        fake_mesh = MagicMock()
        fake_mesh.__class__ = MagicMock  # not a MultiBlock
        fake_reader.read.return_value = fake_mesh

        sim = SimulationData.__new__(SimulationData)
        sim._meshes = {}
        sim._time_steps = [0]
        sim._reader = fake_reader
        sim._format = fmt
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        return sim

    def test_pvd_reader_does_not_call_enable_all_arrays(self):
        """get_mesh on a PVD reader must not call EnableAllCellArrays."""
        sim = self._make_reader_sim("pvd")
        # Should not raise AttributeError
        try:
            sim.get_mesh(0)
        except AttributeError as e:
            pytest.fail(f"get_mesh raised AttributeError for pvd format: {e}")

    def test_ensight_reader_does_not_call_enable_all_arrays(self):
        """get_mesh on an EnSight reader must not call EnableAllCellArrays."""
        sim = self._make_reader_sim("ensight")
        try:
            sim.get_mesh(0)
        except AttributeError as e:
            pytest.fail(f"get_mesh raised AttributeError for ensight format: {e}")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_data_loader.py::TestEnableAllArraysGuard -v
```

Expected: FAIL — `AttributeError` because `EnableAllCellArrays` is called unconditionally.

- [ ] **Step 3: Guard the `EnableAllCellArrays` block in `get_mesh()`**

In `data_loader.py`, in `get_mesh()`, wrap the enable-all block:

```python
if self._reader is not None:
    if self._format in ("openfoam", "openfoam_decomposed"):
        vtk_r = self._reader._reader
        vtk_r.EnableAllCellArrays()
        vtk_r.EnableAllPointArrays()

    self._reader.set_active_time_point(step_index)
    mesh = self._reader.read()
    ...
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_data_loader.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/data_loader.py tests/test_data_loader.py
git commit -m "fix: guard EnableAllCellArrays to openfoam formats only in get_mesh()"
```

---

### Task 4: Refactor `_detect_format()` to use `SUFFIX_MAP`

Replace the chain of `elif suffix == ...` checks with a flat dict lookup. Preserves existing OpenFOAM decomposed detection and directory fallback.

**Files:**
- Modify: `scripts/data_loader.py` (`_detect_format`)
- Modify: `tests/test_data_loader.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_data_loader.py`:

```python
class TestDetectFormat:
    """_detect_format() assigns the correct self._format for each extension."""

    def _detect(self, suffix):
        """Helper: create a SimulationData with the given suffix and return _format.

        Path.is_dir is mocked to False so unsupported extensions reliably raise
        ValueError instead of accidentally matching the directory fallback.
        """
        sim = SimulationData.__new__(SimulationData)
        sim.case_path = Path(f"dummy{suffix}")
        sim._reader = None
        sim._time_steps = []
        sim._meshes = {}
        sim._format = None
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        with patch.object(Path, "is_dir", return_value=False):
            sim._detect_format()
        return sim._format

    def test_vtp(self):      assert self._detect(".vtp")  == "vtp"
    def test_stl(self):      assert self._detect(".stl")  == "stl"
    def test_obj(self):      assert self._detect(".obj")  == "obj"
    def test_ply(self):      assert self._detect(".ply")  == "ply"
    def test_case(self):     assert self._detect(".case") == "ensight"
    def test_cgns(self):     assert self._detect(".cgns") == "cgns"
    def test_exo(self):      assert self._detect(".exo")  == "exodus"
    def test_e(self):        assert self._detect(".e")    == "exodus"
    def test_ex2(self):      assert self._detect(".ex2")  == "exodus"
    def test_xdmf(self):     assert self._detect(".xdmf") == "xdmf"
    def test_xmf(self):      assert self._detect(".xmf")  == "xdmf"
    def test_hdf5(self):     assert self._detect(".hdf5") == "hdf5"
    def test_med(self):      assert self._detect(".med")  == "med"
    def test_msh(self):      assert self._detect(".msh")  == "msh"

    def test_unsupported_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            self._detect(".abc")

    def test_h5_raises(self):
        """`.h5` is intentionally unsupported — conflicts with FLUENT CFF."""
        with pytest.raises(ValueError):
            self._detect(".h5")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_data_loader.py::TestDetectFormat -v
```

Expected: most FAIL — new extensions not yet in `_detect_format()`.

- [ ] **Step 3: Refactor `_detect_format()` with `SUFFIX_MAP`**

Replace the body of `_detect_format()` in `data_loader.py`:

```python
_SUFFIX_MAP = {
    # VTK family
    ".pvd": "pvd", ".vtu": "vtk_single", ".vtk": "vtk_single", ".vtp": "vtp",
    # Surface meshes
    ".stl": "stl", ".obj": "obj", ".ply": "ply",
    # CFD time-series
    ".case": "ensight", ".cgns": "cgns",
    # FEA time-series
    ".exo": "exodus", ".e": "exodus", ".ex2": "exodus",
    # XDMF + HDF5 pair
    ".xdmf": "xdmf", ".xmf": "xdmf",
    # meshio-backed (.h5 excluded — PyVista maps it to FLUENTCFFReader)
    ".hdf5": "hdf5", ".med": "med", ".msh": "msh",
}

def _detect_format(self):
    """Auto-detect simulation file format from path extension."""
    suffix = self.case_path.suffix.lower()

    # OpenFOAM: check for decomposed (processor*) directories
    if suffix in (".foam", ".openfoam"):
        case_dir = self.case_path.parent
        proc_dirs = sorted(glob.glob(str(case_dir / "processor*")))
        if proc_dirs:
            print(f"🔍 Detected {len(proc_dirs)} processor directories — using decomposed mode.")
            self._format = "openfoam_decomposed"
            self._is_decomposed = True
        else:
            print("🔍 No processor directories found — using reconstructed mode.")
            self._format = "openfoam"
        return

    # All other formats via SUFFIX_MAP
    if suffix in self._SUFFIX_MAP:
        self._format = self._SUFFIX_MAP[suffix]
        return

    # Directory of VTK files
    if self.case_path.is_dir():
        self._format = "vtk_directory"
        return

    raise ValueError(
        f"Unsupported format: '{suffix}'. "
        f"Supported extensions: .foam, .openfoam, "
        + ", ".join(sorted(self._SUFFIX_MAP.keys()))
        + ", or a directory of .vtu files."
    )
```

Note: `_SUFFIX_MAP` is defined as a class attribute above `__init__`.

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_data_loader.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/data_loader.py tests/test_data_loader.py
git commit -m "refactor: _detect_format() uses SUFFIX_MAP dict — adds detection for 11 new formats"
```

---

### Task 5: Add single-mesh loaders (VTP, STL, OBJ, PLY)

These formats contain one static mesh (no time steps). All four share the same implementation pattern.

**Files:**
- Modify: `scripts/data_loader.py`
- Modify: `tests/test_data_loader.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_data_loader.py`:

```python
class TestSingleMeshLoaders:
    """VTP, STL, OBJ, PLY: one time step, mesh stored under (0, 'default')."""

    def _make_sim(self, suffix):
        sim = SimulationData.__new__(SimulationData)
        sim.case_path = Path(f"dummy{suffix}")
        sim._meshes = {}
        sim._time_steps = []
        sim._reader = None
        sim._format = suffix.lstrip(".")
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        return sim

    @pytest.mark.parametrize("suffix,method", [
        (".vtp", "load_vtp"),
        (".stl", "load_stl"),
        (".obj", "load_obj"),
        (".ply", "load_ply"),
    ])
    def test_loads_single_mesh(self, suffix, method):
        fake_mesh = MagicMock()
        sim = self._make_sim(suffix)
        with patch("data_loader.pv.read", return_value=fake_mesh):
            getattr(sim, method)()
        assert sim.time_steps == [0]
        assert sim.get_mesh(0) is fake_mesh

    @pytest.mark.parametrize("suffix,method", [
        (".vtp", "load_vtp"),
        (".stl", "load_stl"),
        (".obj", "load_obj"),
        (".ply", "load_ply"),
    ])
    def test_sets_format(self, suffix, method):
        sim = self._make_sim(suffix)
        with patch("data_loader.pv.read", return_value=MagicMock()):
            getattr(sim, method)()
        assert sim._format == suffix.lstrip(".")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_data_loader.py::TestSingleMeshLoaders -v
```

Expected: FAIL — `load_vtp`, `load_stl`, `load_obj`, `load_ply` do not exist yet.

- [ ] **Step 3: Add the four loaders to `data_loader.py`**

Add after `load_vtk_directory`:

```python
def load_vtp(self):
    """Load a VTK PolyData file (.vtp) — surface mesh, one time step."""
    self._time_steps = [0]
    self._meshes[(0, "default")] = pv.read(str(self.case_path))
    self._format = "vtp"

def load_stl(self):
    """Load an STL surface mesh — one time step."""
    self._time_steps = [0]
    self._meshes[(0, "default")] = pv.read(str(self.case_path))
    self._format = "stl"

def load_obj(self):
    """Load a Wavefront OBJ surface mesh — one time step."""
    self._time_steps = [0]
    self._meshes[(0, "default")] = pv.read(str(self.case_path))
    self._format = "obj"

def load_ply(self):
    """Load a PLY point cloud or surface mesh — one time step."""
    self._time_steps = [0]
    self._meshes[(0, "default")] = pv.read(str(self.case_path))
    self._format = "ply"
```

Also update `load()` dispatch dict to include the new formats (add to the existing dispatch block):

```python
"vtp":    self.load_vtp,
"stl":    self.load_stl,
"obj":    self.load_obj,
"ply":    self.load_ply,
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_data_loader.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/data_loader.py tests/test_data_loader.py
git commit -m "feat: add load_vtp, load_stl, load_obj, load_ply single-mesh loaders"
```

---

### Task 6: Add time-series reader loaders (EnSight, CGNS, Exodus, XDMF)

These formats have time steps and use PyVista reader objects. `get_mesh()` already handles the reader path after the bug fixes in Tasks 2–3.

**Files:**
- Modify: `scripts/data_loader.py`
- Modify: `tests/test_data_loader.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_data_loader.py`:

```python
class TestReaderLoaders:
    """EnSight, CGNS, Exodus, XDMF: use pv reader objects with time_values."""

    def _make_fake_reader(self, time_values=(0.0, 1.0)):
        reader = MagicMock()
        reader.time_values = list(time_values)
        return reader

    def _make_sim(self, fmt):
        sim = SimulationData.__new__(SimulationData)
        sim.case_path = Path(f"dummy.{fmt}")
        sim._meshes = {}
        sim._time_steps = []
        sim._reader = None
        sim._format = fmt
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        return sim

    @pytest.mark.parametrize("fmt,method,pv_class", [
        ("ensight", "load_ensight", "EnSightReader"),
        ("cgns",    "load_cgns",    "CGNSReader"),
        ("exodus",  "load_exodus",  "ExodusIIReader"),
        ("xdmf",    "load_xdmf",   "XdmfReader"),
    ])
    def test_sets_reader_and_time_steps(self, fmt, method, pv_class):
        fake_reader = self._make_fake_reader()
        sim = self._make_sim(fmt)
        with patch(f"data_loader.pv.{pv_class}", return_value=fake_reader):
            getattr(sim, method)()
        assert sim._reader is fake_reader
        assert sim._time_steps == [0.0, 1.0]
        assert sim._format == fmt

    def test_cgns_enables_all_bases_and_families(self):
        fake_reader = self._make_fake_reader()
        sim = self._make_sim("cgns")
        with patch("data_loader.pv.CGNSReader", return_value=fake_reader):
            sim.load_cgns()
        fake_reader.enable_all_bases.assert_called_once()
        fake_reader.enable_all_families.assert_called_once()

    def test_empty_time_values_defaults_to_zero(self):
        """If reader has no time values, fall back to [0]."""
        fake_reader = self._make_fake_reader(time_values=[])
        sim = self._make_sim("ensight")
        with patch("data_loader.pv.EnSightReader", return_value=fake_reader):
            sim.load_ensight()
        assert sim._time_steps == [0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_data_loader.py::TestReaderLoaders -v
```

Expected: FAIL — methods do not exist yet.

- [ ] **Step 3: Add the four reader loaders to `data_loader.py`**

Add after the single-mesh loaders:

```python
# ── CFD / FEA time-series loaders ────────────────────────────────────────

def load_ensight(self):
    """Load an EnSight Gold case file (.case) with optional time series."""
    reader = pv.EnSightReader(str(self.case_path))
    self._time_steps = list(reader.time_values) or [0]
    self._reader = reader
    self._format = "ensight"

def load_cgns(self):
    """Load a CGNS (CFD General Notation System) file with optional time series."""
    reader = pv.CGNSReader(str(self.case_path))
    reader.enable_all_bases()
    reader.enable_all_families()
    self._time_steps = list(reader.time_values) or [0]
    self._reader = reader
    self._format = "cgns"

def load_exodus(self):
    """Load an Exodus II file (.exo/.e/.ex2) as used in FEA and Sandia codes."""
    reader = pv.ExodusIIReader(str(self.case_path))
    self._time_steps = list(reader.time_values) or [0]
    self._reader = reader
    self._format = "exodus"

def load_xdmf(self):
    """Load an XDMF file (.xdmf/.xmf), typically paired with a companion HDF5 store.

    The companion .h5 file must be in the same directory as the .xdmf file.
    """
    reader = pv.XdmfReader(str(self.case_path))
    self._time_steps = list(reader.time_values) or [0]
    self._reader = reader
    self._format = "xdmf"
```

Update `load()` dispatch:

```python
"ensight": self.load_ensight,
"cgns":    self.load_cgns,
"exodus":  self.load_exodus,
"xdmf":    self.load_xdmf,
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_data_loader.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/data_loader.py tests/test_data_loader.py
git commit -m "feat: add load_ensight, load_cgns, load_exodus, load_xdmf time-series loaders"
```

---

### Task 7: Add meshio-backed loaders (HDF5, MED, MSH)

These formats use a shared `_read_via_meshio()` helper with a lazy `import meshio`. The import only happens when the method is called, not at module load time.

**Files:**
- Modify: `scripts/data_loader.py`
- Modify: `tests/test_data_loader.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_data_loader.py`:

```python
class TestMeshioLoaders:
    """HDF5, MED, MSH: use meshio (lazy import) via _read_via_meshio helper."""

    def _make_sim(self, suffix):
        sim = SimulationData.__new__(SimulationData)
        sim.case_path = Path(f"dummy{suffix}")
        sim._meshes = {}
        sim._time_steps = []
        sim._reader = None
        sim._format = None
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        return sim

    @pytest.mark.parametrize("suffix,method,fmt", [
        (".hdf5", "load_hdf5", "hdf5"),
        (".med",  "load_med",  "med"),
        (".msh",  "load_msh",  "msh"),
    ])
    def test_loads_single_mesh_via_meshio(self, suffix, method, fmt):
        fake_pv_mesh = MagicMock()
        fake_meshio_mesh = MagicMock()
        sim = self._make_sim(suffix)
        with patch.dict("sys.modules", {"meshio": MagicMock(read=MagicMock(return_value=fake_meshio_mesh))}):
            with patch("data_loader.pv.from_meshio", return_value=fake_pv_mesh):
                getattr(sim, method)()
        assert sim.time_steps == [0]
        assert sim.get_mesh(0) is fake_pv_mesh
        assert sim._format == fmt

    def test_missing_meshio_raises_import_error(self):
        """If meshio is not installed, a clear ImportError with install hint is raised."""
        sim = self._make_sim(".hdf5")
        with patch.dict("sys.modules", {"meshio": None}):
            with pytest.raises(ImportError, match="pip install meshio"):
                sim.load_hdf5()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_data_loader.py::TestMeshioLoaders -v
```

Expected: FAIL — methods do not exist yet.

- [ ] **Step 3: Add `_read_via_meshio` helper and three public loaders**

Add to `data_loader.py` after the XDMF loader:

```python
# ── meshio-backed loaders ─────────────────────────────────────────────────

def _read_via_meshio(self) -> pv.DataSet:
    """Read self.case_path using meshio and return a PyVista dataset.

    meshio is imported lazily so it is only required when actually used.
    Install with: pip install meshio
    """
    try:
        import meshio
    except ImportError:
        raise ImportError(
            "meshio is required for this format. "
            "Install with: pip install meshio"
        )
    return pv.from_meshio(meshio.read(str(self.case_path)))

def load_hdf5(self):
    """Load a generic HDF5 mesh file (.hdf5) via meshio.

    Note: .h5 files are intentionally unsupported here — PyVista maps .h5
    to its FLUENTCFFReader. Use .hdf5 for generic HDF5/meshio-backed meshes.
    Requires: pip install meshio h5py
    """
    self._time_steps = [0]
    self._meshes[(0, "default")] = self._read_via_meshio()
    self._format = "hdf5"

def load_med(self):
    """Load a Salome MED file (.med) via meshio.

    Requires: pip install meshio
    """
    self._time_steps = [0]
    self._meshes[(0, "default")] = self._read_via_meshio()
    self._format = "med"

def load_msh(self):
    """Load a Gmsh mesh file (.msh) via meshio.

    Requires: pip install meshio
    """
    self._time_steps = [0]
    self._meshes[(0, "default")] = self._read_via_meshio()
    self._format = "msh"
```

Update `load()` dispatch:

```python
"hdf5": self.load_hdf5,
"med":  self.load_med,
"msh":  self.load_msh,
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_data_loader.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/data_loader.py tests/test_data_loader.py
git commit -m "feat: add load_hdf5, load_med, load_msh via lazy meshio import"
```

---

### Task 8: Refactor `load()` to use dispatch dict + rename private loaders

Clean up `load()` to use the dispatch dict pattern. Also rename the two remaining private OpenFOAM loaders to public names (`load_openfoam`, `load_openfoam_decomposed`) for API consistency.

**Files:**
- Modify: `scripts/data_loader.py`

- [ ] **Step 1: Run existing tests to confirm baseline**

```bash
pytest tests/test_data_loader.py -v
```

Expected: all PASS (no new test needed — this is a refactor only)

- [ ] **Step 2: Rename private OpenFOAM loaders and update `load()` dispatch**

In `data_loader.py`:

- Rename `_load_openfoam` → `load_openfoam`
- Rename `_load_decomposed` → `load_openfoam_decomposed`
- Update `load()` to use a dispatch dict:

```python
def load(self):
    """Load simulation data using the auto-detected format. Returns self."""
    dispatch = {
        "openfoam":            self.load_openfoam,
        "openfoam_decomposed": self.load_openfoam_decomposed,
        "pvd":                 self.load_pvd,
        "vtk_single":          self.load_vtk_single,
        "vtk_directory":       self.load_vtk_directory,
        "vtp":                 self.load_vtp,
        "stl":                 self.load_stl,
        "obj":                 self.load_obj,
        "ply":                 self.load_ply,
        "ensight":             self.load_ensight,
        "cgns":                self.load_cgns,
        "exodus":              self.load_exodus,
        "xdmf":                self.load_xdmf,
        "hdf5":                self.load_hdf5,
        "med":                 self.load_med,
        "msh":                 self.load_msh,
    }
    dispatch[self._format]()
    return self
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/test_data_loader.py -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/data_loader.py
git commit -m "refactor: load() uses dispatch dict; OpenFOAM loaders are now public methods"
```

---

### Task 9: Update `summary()` and docstrings

Update the class docstring and `summary()` to reflect new supported formats.

**Files:**
- Modify: `scripts/data_loader.py`

- [ ] **Step 1: Update the class docstring**

Replace the `Supports:` block in the `SimulationData` docstring:

```python
"""
Iterates through 4D simulation states from a wide range of 3D file formats.

Supported formats:
  OpenFOAM:  .foam, .openfoam (reconstructed and decomposed/parallel)
  VTK:       .pvd, .vtu, .vtk, .vtp, or a directory of .vtu files
  Surface:   .stl, .obj, .ply
  CFD:       .case (EnSight Gold), .cgns
  FEA:       .exo, .e, .ex2 (Exodus II)
  XDMF:      .xdmf, .xmf (companion .h5 must be co-located)
  meshio:    .hdf5, .med (Salome), .msh (Gmsh)  — requires pip install meshio

Each format has a standalone public loader (e.g. sim.load_ensight()) that
can be called directly without going through auto-detection.

Usage:
    sim = SimulationData("path/to/case.foam").load()
    for time, mesh in sim:
        print(time, mesh.n_points)
"""
```

- [ ] **Step 2: Update `summary()` format line**

The `summary()` method already prints `self._format`, which is set by every loader, so no logic change needed. Just verify output looks right:

```bash
python -c "
from scripts.data_loader import SimulationData
from unittest.mock import MagicMock, patch
sim = SimulationData.__new__(SimulationData)
sim.case_path = __import__('pathlib').Path('dummy.stl')
sim._meshes = {(0, 'default'): MagicMock(n_points=100, n_cells=50, point_data={}, cell_data={})}
sim._time_steps = [0]
sim._reader = None
sim._format = 'stl'
sim._is_decomposed = False
sim._proc_readers = []
sim._proc_foam_files = []
print(sim.summary())
"
```

Expected output includes `📐 Format:      stl`.

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/test_data_loader.py -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/data_loader.py
git commit -m "docs: update SimulationData docstring and summary() to reflect all supported formats"
```
