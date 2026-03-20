"""
data_loader.py — Scientific Data Architect Module

Loads and iterates through 4D simulation data from OpenFOAM / VTK files.
Supports both reconstructed and decomposed (parallel) OpenFOAM cases.

Corresponds to: agents.yaml → data_architect
Corresponds to: tasks.yaml  → data_extraction_task
"""

import os
import glob
import tempfile
from pathlib import Path
from typing import Optional

import pyvista as pv
import numpy as np


class SimulationData:
    """
    Iterates through 4D simulation states from a wide range of 3D file formats.

    Supported formats:
      OpenFOAM:  .foam, .openfoam (reconstructed and decomposed/parallel)
      VTK:       .pvd, .vtu, .vtk, .vtp, or a directory of .vtu files
      Surface:   .stl, .obj, .ply
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
        """
        Initialize the data loader.
        
        Args:
            case_path: Path to the OpenFOAM .foam file, .pvd collection,
                       or directory containing .vtu time-step files.
        """
        self.case_path = Path(case_path)
        self._reader = None
        self._time_steps = []
        self._meshes = {}
        self._format = None
        self._is_decomposed = False
        self._proc_readers = []
        self._proc_foam_files = []  # track temp .foam files for cleanup
        self._detect_format()

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
            "abaqus_inp":          self.load_abaqus_inp,
        }
        dispatch[self._format]()
        return self

    def load_openfoam_decomposed(self):
        """
        Load a decomposed (parallel) OpenFOAM case.
        
        Reads each processor* directory separately via individual
        OpenFOAMReaders, then merges the internal meshes at each
        time step using pyvista.merge().
        """
        case_dir = self.case_path.parent
        proc_dirs = sorted(glob.glob(str(case_dir / "processor*")))
        
        if not proc_dirs:
            raise FileNotFoundError(
                f"No processor* directories found in {case_dir}"
            )

        # Create temporary .foam marker files inside each processor dir
        self._proc_readers = []
        for proc_dir in proc_dirs:
            foam_file = os.path.join(proc_dir, "_temp_reader.foam")
            # Create empty .foam marker
            with open(foam_file, "w") as f:
                pass
            self._proc_foam_files.append(foam_file)
            
            reader = pv.OpenFOAMReader(foam_file)
            # Enable all field arrays
            vtk_r = reader._reader
            vtk_r.EnableAllCellArrays()
            vtk_r.EnableAllPointArrays()
            vtk_r.EnableAllPatchArrays()
            vtk_r.Update()
            
            # Force a read to ensure arrays are discovered early
            try:
                if len(reader.time_values) > 0:
                    reader.set_active_time_point(0)
                    reader.read()
            except:
                pass
                
            self._proc_readers.append(reader)

        # Get time steps from first processor
        self._time_steps = list(self._proc_readers[0].time_values)
        print(f"✅ Decomposed case loaded: {len(proc_dirs)} processors, "
              f"{len(self._time_steps)} time steps")
        print(f"   Processors: {[os.path.basename(p) for p in proc_dirs]}")
        print(f"   Time range: {self._time_steps[0]} → {self._time_steps[-1]}")

    def load_openfoam(self):
        """Load a reconstructed OpenFOAM case."""
        reader = pv.OpenFOAMReader(str(self.case_path))
        vtk_r = reader._reader
        vtk_r.EnableAllCellArrays()
        vtk_r.EnableAllPointArrays()
        vtk_r.EnableAllPatchArrays()
        vtk_r.Update()
        self._time_steps = list(reader.time_values)
        self._reader = reader

    def load_pvd(self):
        """Load a PVD XML collection that indexes multiple VTK files with timestamps."""
        reader = pv.PVDReader(str(self.case_path))
        self._time_steps = list(reader.time_values) or [0]
        self._reader = reader
        self._format = "pvd"

    def load_vtk_directory(self):
        """Load a directory of .vtu files, treating each file as one time step."""
        vtu_files = sorted(glob.glob(str(self.case_path / "*.vtu")))
        self._time_steps = list(range(len(vtu_files)))
        for i, f in enumerate(vtu_files):
            self._meshes[(i, "default")] = pv.read(f)
        self._format = "vtk_directory"

    def load_vtk_single(self):
        """Load a single VTK/VTU/VTP file (one time step)."""
        self._time_steps = [0]
        self._meshes[(0, "default")] = pv.read(str(self.case_path))
        self._format = "vtk_single"

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

    def load_abaqus_inp(self):
        """Load an Abaqus input deck (.inp) via meshio.

        Reads mesh geometry, node sets, and element sets. Field results
        are stored in Abaqus .odb files (proprietary binary) and are not
        supported. If you need field data, export from Abaqus to VTK/VTU.
        Requires: pip install meshio
        """
        self._time_steps = [0]
        self._meshes[(0, "default")] = self._read_via_meshio()
        self._format = "abaqus_inp"

    @property
    def time_steps(self) -> list:
        """Return the available time steps."""
        return self._time_steps

    @property
    def n_steps(self) -> int:
        """Number of available time steps."""
        return len(self._time_steps)

    @property
    def fields(self) -> list:
        """Return a sorted list of unique point and cell field names."""
        mesh = self.get_mesh(0)
        if mesh is None:
            return []
        all_fields = list(mesh.point_data.keys()) + list(mesh.cell_data.keys())
        return sorted(list(set(all_fields)))

    def get_mesh(self, step_index: int, part: str = "internalMesh") -> Optional[pv.DataSet]:
        """
        Get the mesh at a specific time-step index.
        
        Args:
            step_index: Zero-based index into the time_steps list.
            part: The name of the mesh part to extract (e.g., "internalMesh", "walls").
        
        Returns:
            A PyVista dataset for the requested time step.
        """
        mesh_key = (step_index, part)
        if mesh_key in self._meshes:
            return self._meshes[mesh_key]

        # Non-OpenFOAM formats store under "default" — fall back when part not found
        default_key = (step_index, "default")
        if default_key in self._meshes:
            return self._meshes[default_key]

        if self._is_decomposed:
            return self._get_decomposed_mesh(step_index, part)

        if self._reader is not None:
            if self._format in ("openfoam", "openfoam_decomposed"):
                vtk_r = self._reader._reader
                vtk_r.EnableAllCellArrays()
                vtk_r.EnableAllPointArrays()

            self._reader.set_active_time_point(step_index)
            mesh = self._reader.read()
            # OpenFOAM reader returns MultiBlock
            if isinstance(mesh, pv.MultiBlock):
                if part in mesh.keys():
                    mesh = mesh[part]
                elif "internalMesh" in mesh.keys():
                    print(f"⚠️ Part '{part}' not found, falling back to 'internalMesh'")
                    mesh = mesh["internalMesh"]
                else:
                    mesh = mesh.combine()
            
            self._meshes[mesh_key] = mesh
            return mesh

        return None

    def _get_decomposed_mesh(self, step_index: int, part: str = "internalMesh") -> Optional[pv.DataSet]:
        """
        Read and merge a decomposed mesh from all processors at a given
        time step.
        """
        parts = []
        for reader in self._proc_readers:
            # Ensure all arrays are enabled for this reader
            vtk_r = reader._reader
            vtk_r.EnableAllCellArrays()
            vtk_r.EnableAllPointArrays()
            vtk_r.EnableAllPatchArrays()
            
            reader.set_active_time_point(step_index)
            block = reader.read()
            if isinstance(block, pv.MultiBlock):
                if part in block.keys():
                    sub = block[part]
                elif "internalMesh" in block.keys():
                    sub = block["internalMesh"]
                else:
                    sub = block.combine()
            else:
                sub = block
                
            if sub is not None and (hasattr(sub, 'n_points') and sub.n_points > 0):
                parts.append(sub)

        if not parts:
            return None

        # Merge all processor chunks into one mesh
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
        """Return a human-readable summary of the loaded dataset."""
        mesh = self.get_mesh(0)
        lines = [
            f"📂 Source:      {self.case_path}",
            f"📐 Format:      {self._format}",
            f"⏱  Time steps:  {self.n_steps}",
            f"⏱  Time range:  {self._time_steps[0]} → {self._time_steps[-1]}" if self._time_steps else "",
        ]
        if mesh:
            lines += [
                f"📍 Points:      {mesh.n_points:,}",
                f"🔷 Cells:       {mesh.n_cells:,}",
                f"📊 Point fields: {', '.join(mesh.point_data.keys()) if mesh.point_data else 'none'}",
                f"📊 Cell fields:  {', '.join(mesh.cell_data.keys()) if mesh.cell_data else 'none'}",
            ]
        if self._is_decomposed:
            lines.append(f"🖥  Processors:  {len(self._proc_readers)}")
        return "\n".join(lines)

    def cleanup(self):
        """Remove temporary .foam files created for decomposed reading."""
        for f in self._proc_foam_files:
            if os.path.exists(f):
                os.remove(f)
        self._proc_foam_files = []

    def __del__(self):
        self.cleanup()
