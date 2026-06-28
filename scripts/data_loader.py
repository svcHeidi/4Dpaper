"""Load and iterate 4D simulation data across supported mesh formats."""

import logging
import os
import glob
import gzip
import struct
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from importlib.metadata import version as _pkg_version

try:
    import pyvista as pv
except Exception as exc:  # pragma: no cover - import-time environment failure
    try:
        _pyvista_ver = _pkg_version("pyvista")
    except Exception:
        _pyvista_ver = "unknown"
    try:
        _vtk_ver = _pkg_version("vtk")
    except Exception:
        _vtk_ver = "unknown"
    raise RuntimeError(
        "PyVista/VTK import failed while loading scientific figure data. "
        f"Installed versions: pyvista={_pyvista_ver}, vtk={_vtk_ver}. "
        "This usually means the environment has an incompatible or broken VTK wheel. "
        "Use the pinned requirements for this project and rebuild the environment."
    ) from exc


LOG = logging.getLogger(__name__)


class SimulationData:
    """Iterates through 4D simulation states from several 3D file formats.

    Supported formats:
      OpenFOAM:  .foam, .openfoam (reconstructed and decomposed/parallel)
      VTK:       .pvd, .vtu, .vtk, .vtp, or a directory of .vtu files
      Surface:   .stl, .obj, .ply, .ply.gz
      CFD:       .case (EnSight Gold), .cgns
      FEA:       .exo, .e, .ex2 (Exodus II)
      XDMF:      .xdmf, .xmf (companion .h5 must be co-located)
      meshio:    .hdf5, .med (Salome), .msh (Gmsh), .inp (Abaqus mesh)  — requires pip install meshio

    Each format has a standalone public loader (e.g. sim.load_ensight()) that
    can be called directly without going through auto-detection.

    Usage:
        sim = SimulationData("path/to/case.foam").load()
        for time, mesh in sim:
            print(time, mesh.n_points)
    """

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
        # Abaqus input deck (mesh only — .odb output databases are proprietary)
        ".inp": "abaqus_inp",
    }

    def __init__(self, case_path: str):
        """Initializes the data loader for one dataset path."""
        self.case_path = Path(case_path)
        self._reader = None
        self._time_steps = []
        self._meshes = {}
        self._format = None
        self._is_decomposed = False
        self._proc_readers = []
        self._proc_foam_files = []
        self._proc_stage_roots = []
        self._detect_format()

    def _detect_format(self):
        """Auto-detect simulation file format from path extension."""
        case_name = self.case_path.name.lower()
        suffix = self.case_path.suffix.lower()

        if case_name.endswith(".ply.gz"):
            self._format = "ply_gzip"
            return

        if case_name.endswith(".vtk.series"):
            self._format = "vtk_series"
            return

        if suffix in (".foam", ".openfoam"):
            case_dir = self.case_path.parent
            proc_dirs = sorted(glob.glob(str(case_dir / "processor*")))
            if proc_dirs:
                self._format = "openfoam_decomposed"
                self._is_decomposed = True
            else:
                self._format = "openfoam"
            return

        if suffix in self._SUFFIX_MAP:
            self._format = self._SUFFIX_MAP[suffix]
            return

        if self.case_path.is_dir():
            self._format = "vtk_directory"
            return

        raise ValueError(
            f"Unsupported format: '{suffix}'. "
            f"Supported extensions: .foam, .openfoam, "
            + ", ".join(sorted(self._SUFFIX_MAP.keys()))
            + ", .ply.gz, or a directory of .vtu files."
        )

    def load(self):
        """Loads simulation data using the auto-detected format."""
        dispatch = {
            "openfoam":            self.load_openfoam,
            "openfoam_decomposed": self.load_openfoam_decomposed,
            "pvd":                 self.load_pvd,
            "vtk_series":          self.load_vtk_series,
            "vtk_single":          self.load_vtk_single,
            "vtk_directory":       self.load_vtk_directory,
            "vtp":                 self.load_vtp,
            "stl":                 self.load_stl,
            "obj":                 self.load_obj,
            "ply":                 self.load_ply,
            "ply_gzip":            self.load_ply,
            "ensight":             self.load_ensight,
            "cgns":                self.load_cgns,
            "exodus":              self.load_exodus,
            "xdmf":                self.load_xdmf,
            "hdf5":                self.load_hdf5,
            "med":                 self.load_med,
            "msh":                 self.load_msh,
            "abaqus_inp":          self.load_abaqus_inp,
        }
        dispatch[self._format]()
        return self

    @staticmethod
    def _configure_openfoam_reader(reader) -> None:
        """Enables all array groups on an OpenFOAM reader."""
        vtk_reader = reader._reader
        vtk_reader.EnableAllCellArrays()
        vtk_reader.EnableAllPointArrays()
        vtk_reader.EnableAllPatchArrays()
        vtk_reader.Update()

    @staticmethod
    def _extract_mesh_part(mesh, part: str):
        """Returns a requested part from a reader result."""
        if not isinstance(mesh, pv.MultiBlock):
            return mesh
        if part in mesh.keys():
            return mesh[part]
        if "internalMesh" in mesh.keys():
            return mesh["internalMesh"]
        return mesh.combine()

    def _set_single_mesh(self, fmt: str, mesh: pv.DataSet) -> None:
        """Stores a single-step mesh under the default part."""
        self._time_steps = [0]
        self._meshes[(0, "default")] = mesh
        self._format = fmt

    def _load_single_mesh_file(self, fmt: str) -> None:
        """Reads a single mesh file into the default slot."""
        self._set_single_mesh(fmt, pv.read(str(self.case_path)))

    def load_openfoam_decomposed(self):
        """Loads a decomposed OpenFOAM case."""
        case_dir = self.case_path.parent
        proc_dirs = sorted(glob.glob(str(case_dir / "processor*")))
        if not proc_dirs:
            raise FileNotFoundError(f"No processor* directories found in {case_dir}")

        self._proc_readers = []
        for proc_dir in proc_dirs:
            source_proc_dir = Path(proc_dir)
            stage_root = Path(tempfile.mkdtemp(prefix=f"4dpaper-{source_proc_dir.name}-"))
            self._proc_stage_roots.append(str(stage_root))
            staged_proc_dir = stage_root / source_proc_dir.name
            staged_proc_dir.mkdir()

            for child in source_proc_dir.iterdir():
                os.symlink(child, staged_proc_dir / child.name)

            foam_file = staged_proc_dir / "_temp_reader.foam"
            foam_file.touch()
            self._proc_foam_files.append(str(foam_file))

            reader = pv.OpenFOAMReader(str(foam_file))
            self._configure_openfoam_reader(reader)

            try:
                if reader.time_values:
                    reader.set_active_time_point(0)
                    reader.read()
            except Exception as exc:
                LOG.debug("Initial decomposed OpenFOAM probe failed for %s: %s", foam_file, exc)

            self._proc_readers.append(reader)

        self._time_steps = list(self._proc_readers[0].time_values)
        LOG.info(
            "Decomposed case: %s processors, %s time steps",
            len(proc_dirs),
            len(self._time_steps),
        )

    def load_openfoam(self):
        """Loads a reconstructed OpenFOAM case."""
        reader = pv.OpenFOAMReader(str(self.case_path))
        self._configure_openfoam_reader(reader)
        self._time_steps = list(reader.time_values)
        self._reader = reader

    def load_pvd(self):
        """Loads a PVD collection."""
        reader = pv.PVDReader(str(self.case_path))
        self._time_steps = list(reader.time_values) or [0]
        self._reader = reader
        self._format = "pvd"

    def load_vtk_series(self):
        """Loads a ParaView `.vtk.series` index."""
        import json

        series_dir = self.case_path.parent
        with open(self.case_path, encoding="utf-8") as f:
            data = json.load(f)
        entries = sorted(data.get("files", []), key=lambda e: e["time"])
        self._time_steps = [e["time"] for e in entries]
        for i, entry in enumerate(entries):
            vtk_path = series_dir / entry["name"]
            self._meshes[(i, "default")] = pv.read(str(vtk_path))
        self._format = "vtk_series"

    def load_vtk_directory(self):
        """Loads a directory of `.vtu` files as a time series."""
        vtu_files = sorted(glob.glob(str(self.case_path / "*.vtu")))
        if not vtu_files:
            raise FileNotFoundError(f"No .vtu files found in {self.case_path}")
        self._time_steps = list(range(len(vtu_files)))
        for i, f in enumerate(vtu_files):
            self._meshes[(i, "default")] = pv.read(f)
        self._format = "vtk_directory"

    def load_vtk_single(self):
        """Loads a single VTK-family file."""
        self._load_single_mesh_file("vtk_single")

    def load_vtp(self):
        """Loads a `.vtp` surface mesh."""
        self._load_single_mesh_file("vtp")

    def load_stl(self):
        """Loads an STL surface mesh."""
        self._load_single_mesh_file("stl")

    def load_obj(self):
        """Loads a Wavefront OBJ surface mesh."""
        self._load_single_mesh_file("obj")

    def load_ply(self):
        """Loads a PLY point cloud or surface mesh.

        The custom parser handles ASCII, `binary_little_endian`, and `.ply.gz`
        files. It falls back to `pyvista.read()` when the layout is unsupported.
        """
        try:
            mesh = _CustomPLYReader.read(self.case_path)
        except (OSError, ValueError, NotImplementedError) as exc:
            LOG.info("Falling back to PyVista for %s: %s", self.case_path, exc)
            mesh = pv.read(str(self.case_path))
        fmt = "ply_gzip" if self.case_path.name.lower().endswith(".ply.gz") else "ply"
        self._set_single_mesh(fmt, mesh)

    @staticmethod
    def compress_ply(
        source_path: str, target_path: Optional[str] = None, compresslevel: int = 9
    ) -> Path:
        """Compresses a `.ply` file into `.ply.gz`.

        Args:
            source_path: Path to an uncompressed `.ply` file.
            target_path: Optional output path. Defaults to `<source>.ply.gz`.
            compresslevel: gzip level from 1 to 9.

        Returns:
            Path to the compressed file.
        """
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"PLY source not found: {src}")
        if src.suffix.lower() != ".ply":
            raise ValueError(f"Expected a .ply source file, got: {src.name}")
        if not (1 <= compresslevel <= 9):
            raise ValueError("compresslevel must be in [1, 9]")

        dst = Path(target_path) if target_path else Path(f"{src}.gz")
        with open(src, "rb") as fin, gzip.open(dst, "wb", compresslevel=compresslevel) as fout:
            shutil.copyfileobj(fin, fout)
        return dst

    def load_ensight(self):
        """Loads an EnSight Gold case file."""
        reader = pv.EnSightReader(str(self.case_path))
        self._time_steps = list(reader.time_values) or [0]
        self._reader = reader
        self._format = "ensight"

    def load_cgns(self):
        """Loads a CGNS file."""
        reader = pv.CGNSReader(str(self.case_path))
        reader.enable_all_bases()
        reader.enable_all_families()
        self._time_steps = list(reader.time_values) or [0]
        self._reader = reader
        self._format = "cgns"

    def load_exodus(self):
        """Loads an Exodus II file."""
        reader = pv.ExodusIIReader(str(self.case_path))
        self._time_steps = list(reader.time_values) or [0]
        self._reader = reader
        self._format = "exodus"

    def load_xdmf(self):
        """Loads an XDMF file with its companion HDF5 store."""
        reader = pv.XdmfReader(str(self.case_path))
        self._time_steps = list(reader.time_values) or [0]
        self._reader = reader
        self._format = "xdmf"

    def _read_via_meshio(self) -> pv.DataSet:
        """Reads `self.case_path` through meshio."""
        try:
            import meshio
        except ImportError:
            raise ImportError(
                "meshio is required for this format. Install with: pip install meshio"
            )
        return pv.from_meshio(meshio.read(str(self.case_path)))

    def load_hdf5(self):
        """Loads a generic `.hdf5` mesh through meshio."""
        self._set_single_mesh("hdf5", self._read_via_meshio())

    def load_med(self):
        """Loads a Salome MED file through meshio."""
        self._set_single_mesh("med", self._read_via_meshio())

    def load_msh(self):
        """Loads a Gmsh mesh file through meshio."""
        self._set_single_mesh("msh", self._read_via_meshio())

    def load_abaqus_inp(self):
        """Loads an Abaqus input deck through meshio."""
        self._set_single_mesh("abaqus_inp", self._read_via_meshio())

    @property
    def time_steps(self) -> list:
        """Returns the available time steps."""
        return self._time_steps

    @property
    def n_steps(self) -> int:
        """Number of available time steps."""
        return len(self._time_steps)

    @property
    def fields(self) -> list:
        """Returns a sorted list of unique point and cell field names."""
        mesh = self.get_mesh(0)
        if mesh is None:
            return []
        all_fields = list(mesh.point_data.keys()) + list(mesh.cell_data.keys())
        return sorted(list(set(all_fields)))

    def get_mesh(self, step_index: int, part: str = "internalMesh") -> Optional[pv.DataSet]:
        """Returns the mesh at one time-step index."""
        mesh_key = (step_index, part)
        if mesh_key in self._meshes:
            return self._meshes[mesh_key]

        default_key = (step_index, "default")
        if default_key in self._meshes:
            return self._meshes[default_key]

        if self._is_decomposed:
            return self._get_decomposed_mesh(step_index, part)

        if self._reader is not None:
            if self._format in ("openfoam", "openfoam_decomposed"):
                self._configure_openfoam_reader(self._reader)

            self._reader.set_active_time_point(step_index)
            mesh = self._extract_mesh_part(self._reader.read(), part)
            self._meshes[mesh_key] = mesh
            return mesh

        return None

    def _get_decomposed_mesh(self, step_index: int, part: str = "internalMesh") -> Optional[pv.DataSet]:
        """Reads and merges a decomposed mesh at one time step."""
        parts = []
        for reader in self._proc_readers:
            self._configure_openfoam_reader(reader)
            reader.set_active_time_point(step_index)
            sub = self._extract_mesh_part(reader.read(), part)

            if sub is not None and hasattr(sub, "n_points") and sub.n_points > 0:
                parts.append(sub)

        if not parts:
            return None

        merged = pv.merge(parts)
        self._meshes[(step_index, part)] = merged
        return merged

    def __iter__(self):
        """Iterate over all time steps, yielding (time_value, mesh) tuples."""
        for i, t in enumerate(self._time_steps):
            yield t, self.get_mesh(i)

    def __len__(self):
        return self.n_steps

    def summary(self) -> str:
        """Returns a human-readable summary of the loaded dataset."""
        mesh = self.get_mesh(0)
        lines = [
            f"Source:       {self.case_path}",
            f"Format:       {self._format}",
            f"Time steps:   {self.n_steps}",
        ]
        if self._time_steps:
            lines.append(f"Time range:   {self._time_steps[0]} -> {self._time_steps[-1]}")
        if mesh is not None:
            lines += [
                f"Points:       {mesh.n_points:,}",
                f"Cells:        {mesh.n_cells:,}",
                f"Point fields: {', '.join(mesh.point_data.keys()) if mesh.point_data else 'none'}",
                f"Cell fields:  {', '.join(mesh.cell_data.keys()) if mesh.cell_data else 'none'}",
            ]
        if self._is_decomposed:
            lines.append(f"Processors:   {len(self._proc_readers)}")
        return "\n".join(lines)

    def cleanup(self):
        """Removes temporary files and directories created for decomposed reads."""
        for f in self._proc_foam_files:
            if os.path.exists(f):
                os.remove(f)
        self._proc_foam_files = []
        for stage_root in self._proc_stage_roots:
            if os.path.exists(stage_root):
                shutil.rmtree(stage_root, ignore_errors=True)
        self._proc_stage_roots = []

    def __del__(self):
        self.cleanup()


class _CustomPLYReader:
    """Minimal PLY reader for ASCII / little-endian binary / gzip-compressed files."""

    _PLY_TO_STRUCT = {
        "char": "b",
        "int8": "b",
        "uchar": "B",
        "uint8": "B",
        "short": "h",
        "int16": "h",
        "ushort": "H",
        "uint16": "H",
        "int": "i",
        "int32": "i",
        "uint": "I",
        "uint32": "I",
        "float": "f",
        "float32": "f",
        "double": "d",
        "float64": "d",
    }

    @classmethod
    def read(cls, path: Path) -> pv.PolyData:
        with cls._open(path) as stream:
            header = cls._parse_header(stream)
            fmt = header["format"]
            if fmt == "ascii":
                points, faces = cls._read_ascii_payload(stream, header)
            elif fmt == "binary_little_endian":
                points, faces = cls._read_binary_little_payload(stream, header)
            elif fmt == "binary_big_endian":
                raise NotImplementedError(
                    "binary_big_endian PLY is not supported by the custom reader."
                )
            else:
                raise ValueError(f"Unsupported PLY format: {fmt}")

        if faces.size:
            return pv.PolyData(points, faces)
        return pv.PolyData(points)

    @staticmethod
    def _open(path: Path):
        if path.name.lower().endswith(".gz"):
            return gzip.open(path, "rb")
        return open(path, "rb")

    @classmethod
    def _parse_header(cls, stream) -> dict:
        first = stream.readline().decode("ascii", errors="strict").strip()
        if first != "ply":
            raise ValueError("Not a valid PLY file: missing 'ply' magic header.")

        fmt = None
        current_element = None
        vertex_count = 0
        face_count = 0
        vertex_properties = []
        face_properties = []

        while True:
            raw = stream.readline()
            if not raw:
                raise ValueError("PLY header terminated unexpectedly.")
            line = raw.decode("ascii", errors="strict").strip()
            if line == "end_header":
                break
            if not line or line.startswith("comment") or line.startswith("obj_info"):
                continue

            tokens = line.split()
            if tokens[0] == "format":
                if len(tokens) < 2:
                    raise ValueError("Malformed format line in PLY header.")
                fmt = tokens[1]
            elif tokens[0] == "element":
                if len(tokens) != 3:
                    raise ValueError("Malformed element line in PLY header.")
                current_element = tokens[1]
                count = int(tokens[2])
                if current_element == "vertex":
                    vertex_count = count
                elif current_element == "face":
                    face_count = count
            elif tokens[0] == "property":
                if current_element == "vertex":
                    if len(tokens) != 3 or tokens[1] == "list":
                        raise ValueError("Only scalar vertex properties are supported.")
                    vertex_properties.append((tokens[2], tokens[1]))
                elif current_element == "face":
                    if tokens[1] == "list":
                        if len(tokens) != 5:
                            raise ValueError("Malformed list property in face element.")
                        face_properties.append(
                            {
                                "kind": "list",
                                "count_type": tokens[2],
                                "item_type": tokens[3],
                                "name": tokens[4],
                            }
                        )
                    else:
                        if len(tokens) != 3:
                            raise ValueError("Malformed scalar face property.")
                        face_properties.append(
                            {"kind": "scalar", "type": tokens[1], "name": tokens[2]}
                        )

        if fmt is None:
            raise ValueError("PLY format not specified in header.")
        coord_names = {name for name, _ in vertex_properties}
        if not {"x", "y", "z"}.issubset(coord_names):
            raise ValueError("PLY vertex element must include x, y, z properties.")

        return {
            "format": fmt,
            "vertex_count": vertex_count,
            "face_count": face_count,
            "vertex_properties": vertex_properties,
            "face_properties": face_properties,
        }

    @classmethod
    def _read_ascii_payload(cls, stream, header: dict):
        vertex_count = header["vertex_count"]
        face_count = header["face_count"]
        vprops = header["vertex_properties"]
        fprops = header["face_properties"]
        vindex = {name: i for i, (name, _) in enumerate(vprops)}

        points = np.zeros((vertex_count, 3), dtype=np.float32)
        for i in range(vertex_count):
            raw = stream.readline()
            if not raw:
                raise ValueError("Unexpected EOF while reading ASCII vertex data.")
            vals = raw.decode("ascii", errors="strict").strip().split()
            if len(vals) < len(vprops):
                raise ValueError("Malformed ASCII vertex row.")
            points[i, 0] = float(vals[vindex["x"]])
            points[i, 1] = float(vals[vindex["y"]])
            points[i, 2] = float(vals[vindex["z"]])

        faces_flat = []
        for _ in range(face_count):
            raw = stream.readline()
            if not raw:
                raise ValueError("Unexpected EOF while reading ASCII face data.")
            vals = raw.decode("ascii", errors="strict").strip().split()
            if not vals:
                continue

            pos = 0
            vertex_indices = None
            for prop in fprops:
                if prop["kind"] == "scalar":
                    if pos >= len(vals):
                        raise ValueError("Malformed ASCII face row.")
                    pos += 1
                    continue

                if pos >= len(vals):
                    raise ValueError("Malformed ASCII face list property.")
                n = int(vals[pos])
                pos += 1
                if n < 0 or (pos + n) > len(vals):
                    raise ValueError("Malformed ASCII face list length.")
                items = [int(v) for v in vals[pos : pos + n]]
                pos += n
                if prop["name"] == "vertex_indices":
                    vertex_indices = items

            if vertex_indices is not None:
                faces_flat.append(len(vertex_indices))
                faces_flat.extend(vertex_indices)

        faces = (
            np.asarray(faces_flat, dtype=np.int64)
            if faces_flat
            else np.array([], dtype=np.int64)
        )
        return points, faces

    @classmethod
    def _read_binary_little_payload(cls, stream, header: dict):
        vertex_count = header["vertex_count"]
        face_count = header["face_count"]
        vprops = header["vertex_properties"]
        fprops = header["face_properties"]

        points = np.zeros((vertex_count, 3), dtype=np.float32)
        for i in range(vertex_count):
            row = {}
            for name, ptype in vprops:
                row[name] = cls._read_scalar(stream, ptype, endian="<")
            points[i, 0] = float(row["x"])
            points[i, 1] = float(row["y"])
            points[i, 2] = float(row["z"])

        faces_flat = []
        for _ in range(face_count):
            for prop in fprops:
                if prop["kind"] == "scalar":
                    cls._read_scalar(stream, prop["type"], endian="<")
                    continue

                n = int(cls._read_scalar(stream, prop["count_type"], endian="<"))
                items = [
                    int(cls._read_scalar(stream, prop["item_type"], endian="<"))
                    for _ in range(n)
                ]
                if prop["name"] == "vertex_indices":
                    faces_flat.append(n)
                    faces_flat.extend(items)

        faces = (
            np.asarray(faces_flat, dtype=np.int64)
            if faces_flat
            else np.array([], dtype=np.int64)
        )
        return points, faces

    @classmethod
    def _read_scalar(cls, stream, ply_type: str, endian: str):
        if ply_type not in cls._PLY_TO_STRUCT:
            raise NotImplementedError(f"Unsupported PLY scalar type: {ply_type}")
        fmt = cls._PLY_TO_STRUCT[ply_type]
        size = struct.calcsize(fmt)
        raw = stream.read(size)
        if len(raw) != size:
            raise ValueError("Unexpected EOF while decoding binary PLY data.")
        return struct.unpack(endian + fmt, raw)[0]
