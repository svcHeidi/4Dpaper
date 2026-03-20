import meshio
import numpy as np

# 1. Setup Geometry: A simple cube or grid
points = np.array([
    [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]
], dtype=float)

# Define a single hexahedron cell (8 nodes)
cells = [("hexahedron", np.array([[0, 1, 2, 3, 4, 5, 6, 7]])) ]

# 2. Create Random Field Data
# Point data: a value for every vertex (8 points)
point_data = {
    "random_scalar": np.random.rand(8),
    "velocity_vector": np.random.rand(8, 3)
}

# Cell data: a value for every element (1 cell)
cell_data = {
    "pressure": [np.random.rand(1)]
}

# 3. Create the Mesh Object
mesh = meshio.Mesh(
    points,
    cells,
    point_data=point_data,
    cell_data=cell_data
)

# 4. Generate Files
# List of formats that support internal field data
data_formats = ["vtu", "vtp", "vtk", "msh", "xdmf", "med"]

# List of formats that are usually geometry-only
geo_formats = ["stl", "obj", "ply"]

print("--- Generating Files with Field Data ---")
for fmt in data_formats:
    try:
        filename = f"test_data.{fmt}"
        mesh.write(filename)
        print(f"✅ Created {filename} (Includes 'random_scalar' and 'velocity_vector')")
    except Exception as e:
        print(f"❌ Failed to create {fmt}: {e}")

print("\n--- Generating Geometry-Only Files ---")
for fmt in geo_formats:
    try:
        filename = f"test_geo.{fmt}"
        # Some formats like STL don't support hex cells, convert to triangles first
        if fmt == "stl" or fmt == "obj":
            # meshio handles the conversion to triangles automatically for some formats
            mesh.write(filename)
        else:
            mesh.write(filename)
        print(f"✅ Created {filename}")
    except Exception as e:
        print(f"⚠️  {fmt} note: {e}")

# 5. Specialized: Create a raw HDF5 file
try:
    import h5py
    with h5py.File("test_data.hdf5", "w") as f:
        f.create_dataset("points", data=points)
        f.create_dataset("field_data", data=np.random.rand(100, 100))
    print("✅ Created test_data.hdf5")
except ImportError:
    print("Skipping HDF5 (h5py not installed)")