"""Tests for 4d-multi-image rendering helpers."""
from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "_extensions" / "4dpaper"))

from lib import render


class TestMultiImageScalarBarArgs:
    def test_primary_source_matches_standard_figure_colorbar(self):
        args = render._multi_image_scalar_bar_args(
            field="Vm",
            axis_color="black",
            source_index=0,
            show_colorbar=True,
        )

        assert args == {"title": "Vm", "color": "black"}

    def test_first_overlay_uses_first_overlay_slot(self):
        args = render._multi_image_scalar_bar_args(
            field="Vm_V",
            axis_color="white",
            source_index=1,
            show_colorbar=True,
        )

        assert args["title"] == "Vm_V"
        assert args["color"] == "white"
        assert args["position_x"] == render._COLORBAR_POSITIONS[0]["position_x"]
        assert args["position_y"] == render._COLORBAR_POSITIONS[0]["position_y"]
        assert args["width"] == render._COLORBAR_POSITIONS[0]["width"]
        assert args["height"] == render._COLORBAR_POSITIONS[0]["height"]

    def test_hidden_colorbar_returns_empty_args(self):
        args = render._multi_image_scalar_bar_args(
            field="Vm",
            axis_color="black",
            source_index=0,
            show_colorbar=False,
        )

        assert args == {}
