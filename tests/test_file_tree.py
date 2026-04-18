"""Tests for file-tree filtering logic in dashboard/file_plugin.py"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.file_plugin import _should_include, _HIDDEN_DIRS


class TestShouldInclude:
    def test_includes_qmd_files(self, tmp_path):
        f = tmp_path / "report.qmd"
        f.write_text("# Hello")
        assert _should_include(f) is True

    def test_includes_bib_files(self, tmp_path):
        f = tmp_path / "refs.bib"
        f.write_text("")
        assert _should_include(f) is True

    def test_excludes_dotfiles(self, tmp_path):
        f = tmp_path / ".hidden"
        f.write_text("")
        assert _should_include(f) is False

    def test_excludes_hidden_dirs(self, tmp_path):
        for d in (".git", ".venv", "__pycache__", "dashboard"):
            p = tmp_path / d
            p.mkdir()
            assert _should_include(p) is False, f"{d} should be excluded"

    def test_includes_normal_subdir(self, tmp_path):
        d = tmp_path / "data"
        d.mkdir()
        assert _should_include(d) is True

    def test_excludes_quarto_files_dir(self, tmp_path):
        d = tmp_path / "paper_files"
        d.mkdir()
        assert _should_include(d) is False

    def test_excludes_files_inside_hidden_dir(self, tmp_path):
        hidden = tmp_path / ".git"
        hidden.mkdir()
        f = hidden / "config"
        f.write_text("")
        assert _should_include(f) is False

    def test_excludes_state_json_files(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        f = state / "camera_fig1.json"
        f.write_text("{}")
        assert _should_include(f) is False

    def test_includes_state_figures_dir(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        figs = state / "figures"
        figs.mkdir()
        assert _should_include(figs) is True


class TestHiddenDirs:
    def test_contains_security_critical_dirs(self):
        assert ".git" in _HIDDEN_DIRS
        assert "dashboard" in _HIDDEN_DIRS
        assert "__pycache__" in _HIDDEN_DIRS
        assert ".venv" in _HIDDEN_DIRS
