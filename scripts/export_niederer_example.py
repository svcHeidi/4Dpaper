"""Export the Niederer slab case as a compact tracked `.vtk.series` example."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_loader import SimulationData


def export_series(source_case: Path, output_dir: Path, base_name: str = "niederer") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    sim = SimulationData(str(source_case)).load()
    entries: list[dict[str, float | str]] = []

    for index, time_value in enumerate(sim.time_steps):
        mesh = sim.get_mesh(index)
        if mesh is None:
            raise RuntimeError(f"Missing mesh for step {index} at time {time_value}")

        surface = mesh.extract_surface(algorithm="dataset_surface")
        for field_name in ("vtkOriginalPointIds", "vtkOriginalCellIds"):
            if field_name in surface.point_data:
                del surface.point_data[field_name]
            if field_name in surface.cell_data:
                del surface.cell_data[field_name]

        frame_name = f"{base_name}_{index:03d}.vtp"
        surface.save(output_dir / frame_name)
        entries.append({"name": frame_name, "time": float(time_value)})

    series_path = output_dir / f"{base_name}.vtk.series"
    series_path.write_text(json.dumps({"files": entries}, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_case", type=Path, help="Path to the source Niederer.foam case")
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Output directory for the exported `.vtk.series` and `.vtp` frames",
    )
    args = parser.parse_args()
    export_series(args.source_case, args.output_dir)


if __name__ == "__main__":
    main()
