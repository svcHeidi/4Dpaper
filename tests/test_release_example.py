"""Smoke tests for the single shipped release example."""

from pathlib import Path

from scripts.data_loader import SimulationData


def test_niederer_release_example_series_loads():
    series_path = (
        Path(__file__).parent.parent
        / "examples"
        / "niederer"
        / "data"
        / "niederer"
        / "niederer.vtk.series"
    )

    sim = SimulationData(str(series_path)).load()
    mesh = sim.get_mesh(0)

    assert sim.n_steps == 8
    assert mesh is not None
    assert mesh.n_points == 11052
    assert mesh.n_cells == 11050
    assert sorted(mesh.point_data.keys()) == [
        "Jsi",
        "Vm",
        "activationTime",
        "externalStimulusCurrent",
        "ionicCurrent",
    ]
