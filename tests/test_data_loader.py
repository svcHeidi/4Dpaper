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
