import meshio
import numpy as np

POINTS = np.array(
    [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 0],
        [0, 1, 0],
        [0, 0, 1],
        [1, 0, 1],
        [1, 1, 1],
        [0, 1, 1],
    ],
    dtype=float,
)
CELLS = [("hexahedron", np.array([[0, 1, 2, 3, 4, 5, 6, 7]]))]
DATA_FORMATS = ["vtu", "vtp", "vtk", "msh", "xdmf", "med"]
GEOMETRY_FORMATS = ["stl", "obj", "ply"]


def build_mesh() -> meshio.Mesh:
    """Build a small hexahedral test mesh."""
    rng = np.random.default_rng(0)
    return meshio.Mesh(
        POINTS,
        CELLS,
        point_data={
            "random_scalar": rng.random(8),
            "velocity_vector": rng.random((8, 3)),
        },
        cell_data={"pressure": [rng.random(1)]},
    )


def main() -> None:
    """Generate fixture files for mesh-format tests."""
    mesh = build_mesh()

    print("--- Generating files with field data ---")
    for fmt in DATA_FORMATS:
        try:
            filename = f"test_data.{fmt}"
            mesh.write(filename)
            print(f"Created {filename}")
        except Exception as exc:
            print(f"Failed to create {fmt}: {exc}")

    print("\n--- Generating geometry-only files ---")
    for fmt in GEOMETRY_FORMATS:
        try:
            filename = f"test_geo.{fmt}"
            mesh.write(filename)
            print(f"Created {filename}")
        except Exception as exc:
            print(f"{fmt} note: {exc}")

    try:
        import h5py

        with h5py.File("test_data.hdf5", "w") as f:
            f.create_dataset("points", data=POINTS)
            f.create_dataset("field_data", data=np.random.default_rng(0).random((100, 100)))
        print("Created test_data.hdf5")
    except ImportError:
        print("Skipping HDF5 (h5py not installed)")


if __name__ == "__main__":
    main()
