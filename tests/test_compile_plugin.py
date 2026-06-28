"""Tests for export-specific compile helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tornado")


def test_validate_standalone_html_rejects_state_figure_references(tmp_path):
    from dashboard.compile_plugin import _validate_standalone_html_output

    html = tmp_path / "paper.html"
    html.write_text('<iframe src="../state/figures/fig-vm.html"></iframe>', encoding="utf-8")

    with pytest.raises(ValueError, match="state/figures"):
        _validate_standalone_html_output(html)


def test_validate_standalone_html_accepts_inlined_export(tmp_path):
    from dashboard.compile_plugin import _validate_standalone_html_output

    html = tmp_path / "paper.html"
    html.write_text('<iframe srcdoc="<html><body>ok</body></html>"></iframe>', encoding="utf-8")

    _validate_standalone_html_output(html)


def test_validate_paperview_html_rejects_missing_asset(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output

    output_dir = tmp_path / "_output"
    output_dir.mkdir()
    html = output_dir / "paper-paperview.html"
    html.write_text('<img src="../state/figures/fig-vm.png">', encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="fig-vm.png"):
        _validate_paperview_html_output(html)


def test_validate_paperview_html_accepts_app_root_state_asset(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output
    from unittest.mock import patch

    project_root = tmp_path / "project"
    output_dir = project_root / "_output"
    figures_dir = project_root / "state" / "figures"
    output_dir.mkdir(parents=True)
    figures_dir.mkdir(parents=True)
    (figures_dir / "fig-vm.png").write_bytes(b"png")

    html = output_dir / "paper-paperview.html"
    html.write_text('<img src="/state/figures/fig-vm.png">', encoding="utf-8")

    with patch("dashboard.compile_plugin._PROJECT_ROOT", project_root):
        _validate_paperview_html_output(html)


def test_validate_paperview_html_rejects_placeholder_warning(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output

    html = tmp_path / "paper-paperview.html"
    html.write_text("⚠ Figure <code>fig-vm</code> not rendered — click Rebuild HTML", encoding="utf-8")

    with pytest.raises(ValueError, match="Static figure generation failed"):
        _validate_paperview_html_output(html)


def test_validate_paperview_html_accepts_existing_assets(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output

    output_dir = tmp_path / "_output"
    figures_dir = tmp_path / "state" / "figures"
    output_dir.mkdir()
    figures_dir.mkdir(parents=True)
    (figures_dir / "fig-vm.png").write_bytes(b"png")

    html = output_dir / "paper-paperview.html"
    html.write_text('<img src="../state/figures/fig-vm.png">', encoding="utf-8")

    _validate_paperview_html_output(html)


def test_rewrite_paperview_asset_urls_for_pdf_converts_state_root_url():
    from dashboard.compile_plugin import _rewrite_paperview_asset_urls_for_pdf

    html = '<img src="/state/figures/fig-vm.png"><img src="../state/figures/fig-at.png">'
    rewritten = _rewrite_paperview_asset_urls_for_pdf(html)

    assert 'src="../state/figures/fig-vm.png"' in rewritten
    assert 'src="../state/figures/fig-at.png"' in rewritten
