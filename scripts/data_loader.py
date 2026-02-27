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
    Iterates through 4D simulation states from OpenFOAM or VTK files.
    
    Supports:
      - Reconstructed cases (time dirs at case root)
      - Decomposed cases (time dirs only inside processor* folders)
      - .pvd collections
      - Single or directory of .vtu files

    Usage:
        sim = SimulationData("path/to/case.foam")
        for state in sim:
            print(state.time, state.mesh.n_points)
    """

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
        """Auto-detect the simulation file format."""
        suffix = self.case_path.suffix.lower()

        if suffix == ".foam" or suffix == ".openfoam":
            case_dir = self.case_path.parent
            proc_dirs = sorted(glob.glob(str(case_dir / "processor*")))
            
            if proc_dirs:
                # Prioritize decomposed case if processor directories exist
                print(f"🔍 Detected {len(proc_dirs)} processor directories — using decomposed mode.")
                self._format = "openfoam_decomposed"
                self._is_decomposed = True
            else:
                print("🔍 No processor directories found — using reconstructed mode.")
                self._format = "openfoam"
                
        elif suffix == ".pvd":
            self._format = "pvd"
        elif suffix in (".vtu", ".vtk"):
            self._format = "vtk_single"
        elif self.case_path.is_dir():
            self._format = "vtk_directory"
        else:
            raise ValueError(
                f"Unsupported format: {suffix}. "
                "Expected .foam, .pvd, .vtu, .vtk, or a directory of VTK files."
            )

    def load(self):
        """Load the simulation data and discover time steps."""
        if self._format == "openfoam_decomposed":
            self._load_decomposed()
        elif self._format == "openfoam":
            self._load_openfoam()
        elif self._format == "pvd":
            self._load_pvd()
        elif self._format == "vtk_directory":
            self._load_vtk_directory()
        elif self._format == "vtk_single":
            self._load_vtk_single()

        return self

    def _load_decomposed(self):
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

    def _load_openfoam(self):
        """Load a reconstructed OpenFOAM case."""
        reader = pv.OpenFOAMReader(str(self.case_path))
        vtk_r = reader._reader
        vtk_r.EnableAllCellArrays()
        vtk_r.EnableAllPointArrays()
        vtk_r.EnableAllPatchArrays()
        vtk_r.Update()
        self._time_steps = list(reader.time_values)
        self._reader = reader

    def _load_pvd(self):
        """Load a PVD collection."""
        reader = pv.PVDReader(str(self.case_path))
        self._time_steps = list(reader.time_values)
        self._reader = reader

    def _load_vtk_directory(self):
        """Load a directory of VTK files."""
        vtu_files = sorted(glob.glob(str(self.case_path / "*.vtu")))
        self._time_steps = list(range(len(vtu_files)))
        self._meshes = {
            i: pv.read(f) for i, f in enumerate(vtu_files)
        }

    def _load_vtk_single(self):
        """Load a single VTK file."""
        self._time_steps = [0]
        self._meshes = {0: pv.read(str(self.case_path))}

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

        if self._is_decomposed:
            return self._get_decomposed_mesh(step_index, part)

        if self._reader is not None:
            # Ensure all arrays are enabled
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
