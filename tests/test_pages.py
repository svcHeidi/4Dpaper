"""Smoke tests for dashboard pages — verify they build without crashing."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


FAKE_CONFIG = {
    "cardiacfoam_root": "/fake/cf",
    "quarto_paper_path": "/fake/paper.qmd",
}


def test_paper_page_builds():
    with patch("dashboard.utils.load_config", return_value=FAKE_CONFIG):
        from dashboard.pages.paper_page import build_paper_page
        page = build_paper_page(config=FAKE_CONFIG)
    assert page is not None
