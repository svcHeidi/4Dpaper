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
