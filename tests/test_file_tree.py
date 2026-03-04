"""Tests for dashboard/file_tree.py"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.file_tree import list_project_files, is_editable, HIDDEN_DIRS


class TestListProjectFiles:
    def test_lists_files_in_directory(self, tmp_path):
        (tmp_path / "report.qmd").write_text("# Hello")
        (tmp_path / "refs.bib").write_text("@article{}")
        result = list_project_files(tmp_path)
        names = [r["name"] for r in result]
        assert "report.qmd" in names
        assert "refs.bib" in names

    def test_lists_subdirectories(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "case.foam").write_text("")
        result = list_project_files(tmp_path)
        dir_names = [r["name"] for r in result if r["is_dir"]]
        assert "data" in dir_names

    def test_hides_filtered_directories(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".venv").mkdir()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "src").mkdir()
        result = list_project_files(tmp_path)
        dir_names = [r["name"] for r in result if r["is_dir"]]
        assert ".git" not in dir_names
        assert ".venv" not in dir_names
        assert "__pycache__" not in dir_names
        assert "src" in dir_names

    def test_sorts_dirs_first_then_files(self, tmp_path):
        (tmp_path / "zebra.qmd").write_text("")
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta.bib").write_text("")
        result = list_project_files(tmp_path)
        # Dirs come first, then files, both alphabetically
        assert result[0]["name"] == "alpha"
        assert result[0]["is_dir"] is True


class TestIsEditable:
    def test_qmd_is_editable(self):
        assert is_editable("report.qmd") is True

    def test_bib_is_editable(self):
        assert is_editable("refs.bib") is True

    def test_yaml_is_editable(self):
        assert is_editable("config.yaml") is True

    def test_css_is_editable(self):
        assert is_editable("style.css") is True

    def test_png_is_not_editable(self):
        assert is_editable("figure.png") is False

    def test_py_is_not_editable(self):
        assert is_editable("script.py") is False

    def test_html_is_not_editable(self):
        assert is_editable("output.html") is False
