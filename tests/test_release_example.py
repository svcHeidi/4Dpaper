"""Smoke tests for the single shipped release example."""

import json
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


def test_niederer_release_example_plot_fixture_is_valid():
    graph_path = (
        Path(__file__).parent.parent
        / "examples"
        / "niederer"
        / "data"
        / "plots"
        / "niederer_signal.json"
    )

    with graph_path.open() as fh:
        fig = json.load(fh)

    assert len(fig["data"]) == 2
    assert fig["data"][0]["type"] == "scatter"
    assert fig["layout"]["template"] == "plotly_white"


def test_niederer_release_example_manuscript_covers_core_shortcodes():
    manuscript_path = (
        Path(__file__).parent.parent / "examples" / "niederer" / "main.qmd"
    )
    manuscript = manuscript_path.read_text()

    assert "{{< 4d-image" in manuscript
    assert "{{< 4d-panel" in manuscript
    assert "{{< 4d-timeseries" in manuscript
    assert "{{< 4d-graph" in manuscript
