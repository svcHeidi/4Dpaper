"""Smoke tests for dashboard pages — verify they build without crashing."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


FAKE_CONFIG = {
    "cardiacfoam_root": "/fake/cf",
    "quarto_paper_path": "/fake/paper.qmd",
    "tutorials": {
        "NiedererEtAl2012": {
            "display_name": "Niederer Et Al. 2012",
            "scripts": [
                {
                    "name": "Line Post-Processing",
                    "module_relpath": "some/script.py",
                    "function": "run_postprocessing",
                    "params": {"output_dir": "out", "show": False},
                }
            ],
            "plots_manifest": "out/plots.json",
        }
    },
}


def test_run_page_builds():
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from dashboard.pages.run_page import build_run_page
        page = build_run_page(tutorial_key="NiedererEtAl2012", config=FAKE_CONFIG)
    assert page is not None


def test_outputs_page_builds():
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from dashboard.pages.outputs_page import build_outputs_page
        page = build_outputs_page(manifest=None)
    assert page is not None


def test_paper_page_builds():
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from dashboard.pages.paper_page import build_paper_page
        page = build_paper_page(config=FAKE_CONFIG)
    assert page is not None
