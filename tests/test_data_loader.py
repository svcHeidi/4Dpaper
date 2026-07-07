"""Tests for scripts/data_loader.py"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pyvista = pytest.importorskip("pyvista", reason="pyvista not installed")

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from data_loader import SimulationData


class TestCacheKeyBugFix:
    """VTK caches use tuple keys."""

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
        assert 0 not in sim._meshes

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
    """`get_mesh` falls back to `(step, "default")`."""

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
        """`get_mesh(0)` returns the default cached mesh."""
        fake_mesh = MagicMock()
        sim = self._make_sim(fake_mesh)
        result = sim.get_mesh(0)
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
    """OpenFOAM array enabling stays scoped to OpenFOAM readers."""

    def _make_reader_sim(self, fmt):
        fake_reader = MagicMock()
        del fake_reader._reader.EnableAllCellArrays
        fake_mesh = MagicMock()
        fake_mesh.__class__ = MagicMock
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
        """Create a stub instance and return the detected format."""
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
    def test_inp(self):      assert self._detect(".inp")  == "abaqus_inp"
    def test_ply_gz(self):   assert self._detect(".ply.gz") == "ply_gzip"

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


class TestPLYCustomReaderAndCompression:
    """Custom PLY reader path and gzip compressor behavior."""

    def _make_sim(self, path):
        sim = SimulationData.__new__(SimulationData)
        sim.case_path = Path(path)
        sim._meshes = {}
        sim._time_steps = []
        sim._reader = None
        sim._format = None
        sim._is_decomposed = False
        sim._proc_readers = []
        sim._proc_foam_files = []
        return sim

    def test_load_ply_prefers_custom_reader(self, tmp_path):
        fake_mesh = MagicMock()
        source = tmp_path / "shape.ply"
        source.write_text(
            "ply\n"
            "format ascii 1.0\n"
            "element vertex 3\n"
            "property float x\n"
            "property float y\n"
            "property float z\n"
            "element face 1\n"
            "property list uchar int vertex_indices\n"
            "end_header\n"
            "0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n"
        )
        sim = self._make_sim(source)
        with patch("data_loader._CustomPLYReader.read", return_value=fake_mesh) as custom_read:
            sim.load_ply()
        custom_read.assert_called_once()
        assert sim._meshes[(0, "default")] is fake_mesh
        assert sim._format == "ply"

    def test_load_ply_falls_back_to_pyvista(self, tmp_path):
        fake_mesh = MagicMock()
        source = tmp_path / "shape.ply"
        source.write_text("ply\nformat ascii 1.0\nend_header\n")
        sim = self._make_sim(source)
        with patch("data_loader._CustomPLYReader.read", side_effect=ValueError("bad ply")):
            with patch("data_loader.pv.read", return_value=fake_mesh) as pv_read:
                sim.load_ply()
        pv_read.assert_called_once()
        assert sim.get_mesh(0) is fake_mesh

    def test_compress_ply_creates_gzip_file(self, tmp_path):
        source = tmp_path / "mesh.ply"
        source.write_text(
            "ply\n"
            "format ascii 1.0\n"
            "element vertex 1\n"
            "property float x\n"
            "property float y\n"
            "property float z\n"
            "element face 0\n"
            "property list uchar int vertex_indices\n"
            "end_header\n"
            "1 2 3\n"
        )
        gz_path = SimulationData.compress_ply(str(source))
        assert gz_path.exists()
        assert gz_path.name.endswith(".ply.gz")
        with gzip.open(gz_path, "rt", encoding="ascii") as f:
            header = f.readline().strip()
        assert header == "ply"

    def test_load_real_ply_gz(self, tmp_path):
        src = DATA_DIR / "airplane.ply"
        if not src.exists():
            pytest.skip(f"Test data not found: {src}")
        gz_path = SimulationData.compress_ply(str(src), str(tmp_path / "airplane.ply.gz"))
        sim = SimulationData(str(gz_path)).load()
        assert sim._format == "ply_gzip"
        assert sim.n_steps == 1
        mesh = sim.get_mesh(0)
        assert mesh is not None
        assert mesh.n_points > 0

    def test_ascii_face_with_scalar_before_vertex_indices(self, tmp_path):
        """Custom ASCII PLY reader must respect face-property order in header."""
        source = tmp_path / "ordered_face_props.ply"
        source.write_text(
            "ply\n"
            "format ascii 1.0\n"
            "element vertex 3\n"
            "property float x\n"
            "property float y\n"
            "property float z\n"
            "element face 1\n"
            "property uchar material_id\n"
            "property list uchar int vertex_indices\n"
            "end_header\n"
            "0 0 0\n"
            "1 0 0\n"
            "0 1 0\n"
            "7 3 0 1 2\n"
        )
        sim = SimulationData(str(source)).load()
        mesh = sim.get_mesh(0)
        assert mesh is not None
        assert mesh.n_points == 3
        assert mesh.n_cells == 1


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
        (".hdf5", "load_hdf5",      "hdf5"),
        (".med",  "load_med",       "med"),
        (".msh",  "load_msh",       "msh"),
        (".inp",  "load_abaqus_inp","abaqus_inp"),
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


# ── Integration tests with real files ─────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"


class TestRealFiles:
    """Load actual files from tests/data/ and verify basic mesh properties.

    These tests are skipped automatically if the data file is not present.
    """

    def _load(self, filename):
        """Helper: load a file and return the SimulationData object."""
        path = DATA_DIR / filename
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        sim = SimulationData(str(path)).load()
        return sim

    def _assert_mesh_ok(self, sim):
        """Assert that at least one time step loaded a non-empty mesh."""
        assert sim.n_steps >= 1
        mesh = sim.get_mesh(0)
        assert mesh is not None
        assert mesh.n_points > 0

    def test_vtk(self):
        self._assert_mesh_ok(self._load("hexbeam.vtk"))

    def test_vtu(self):
        self._assert_mesh_ok(self._load("ref_block.vtu"))

    def test_ply(self):
        self._assert_mesh_ok(self._load("airplane.ply"))

    def test_stl(self):
        self._assert_mesh_ok(self._load("base.stl"))

    def test_obj(self):
        self._assert_mesh_ok(self._load("sphere.obj"))

    def test_vtp(self):
        self._assert_mesh_ok(self._load("track0.vtp"))

    def test_pvd(self):
        sim = self._load("pvd_example/bi_ventricular_fiber.pvd")
        self._assert_mesh_ok(sim)
        assert sim.n_steps >= 1

    def test_vtk_series_generated_from_local_vtk_fixtures(self, tmp_path):
        """A .vtk.series index loads referenced files sorted by time."""
        src_a = DATA_DIR / "hexbeam.vtk"
        src_b = DATA_DIR / "rectilinear.vtk"
        if not src_a.exists() or not src_b.exists():
            pytest.skip("VTK fixtures not found for .vtk.series smoke test")

        shutil.copy2(src_a, tmp_path / "frame_a.vtk")
        shutil.copy2(src_b, tmp_path / "frame_b.vtk")
        series_path = tmp_path / "generated.vtk.series"
        series_path.write_text(
            json.dumps(
                {
                    "files": [
                        {"name": "frame_b.vtk", "time": 2.0},
                        {"name": "frame_a.vtk", "time": 1.0},
                    ]
                }
            ),
            encoding="utf-8",
        )

        sim = SimulationData(str(series_path)).load()
        assert sim._format == "vtk_series"
        assert sim.time_steps == [1.0, 2.0]
        assert sim.n_steps == 2
        self._assert_mesh_ok(sim)

    def test_msh(self):
        # Requires meshio: pip install meshio
        try:
            self._assert_mesh_ok(self._load("slab_cubic.msh"))
        except ImportError as exc:
            pytest.skip(str(exc))

    def test_xdmf(self):
        # Requires an XDMF file with time steps and a companion .h5
        self._assert_mesh_ok(self._load("fiber_directions.xdmf"))

    def test_xdmf_missing_h5_companion_fails_clearly(self, tmp_path):
        src = DATA_DIR / "fiber_directions.xdmf"
        if not src.exists():
            pytest.skip(f"Test data not found: {src}")

        missing_companion = tmp_path / src.name
        shutil.copy2(src, missing_companion)
        sim = SimulationData(str(missing_companion)).load()
        mesh = sim.get_mesh(0)

        assert mesh is None or getattr(mesh, "n_points", 0) == 0

    def test_med(self):
        try:
            self._assert_mesh_ok(self._load("test_data.med"))
        except ImportError as exc:
            pytest.skip(str(exc))
        except Exception as exc:
            pytest.skip(f"MED fixture not loadable in this environment: {exc}")

    def test_hdf5(self):
        try:
            self._assert_mesh_ok(self._load("test_data.hdf5"))
        except ImportError as exc:
            pytest.skip(str(exc))
        except Exception as exc:
            pytest.skip(f"HDF5 fixture not loadable in this environment: {exc}")


class TestDecomposedRelativePathStaging:
    """Decomposed cases must stage resolvable symlinks even from a relative path."""

    def _build_fake_decomposed_case(self, root: Path) -> Path:
        case_dir = root / "case"
        case_dir.mkdir()
        for proc in ("processor0", "processor1"):
            mesh_dir = case_dir / proc / "constant" / "polyMesh"
            mesh_dir.mkdir(parents=True)
            (mesh_dir / "points").write_text("()")
            (case_dir / proc / "0").mkdir()
        foam = case_dir / "case.foam"
        foam.write_text("")
        return foam

    def test_relative_case_path_stages_resolvable_symlinks(self, tmp_path, monkeypatch):
        foam = self._build_fake_decomposed_case(tmp_path)
        monkeypatch.chdir(tmp_path)

        rel_foam = foam.relative_to(tmp_path)
        assert not rel_foam.is_absolute()

        sim = SimulationData(str(rel_foam))
        # The reader will still fail on a mesh-less fake case; the bug under
        # test is purely that the staged processor symlinks must not dangle.
        try:
            sim.load_openfoam_decomposed()
        except Exception:
            pass

        assert sim._proc_stage_roots, "no processor staging dirs were created"
        dangling = []
        for stage_root in sim._proc_stage_roots:
            for link in Path(stage_root).rglob("*"):
                if link.is_symlink() and not link.resolve().exists():
                    dangling.append(str(link))
        assert not dangling, f"dangling staged symlinks: {dangling}"
