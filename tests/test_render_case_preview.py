"""Tests for the standalone case-preview render script."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import dashboard.upload_plugin as upload_plugin
from scripts.render_case_preview import _fields_at_step, _select_field

_PROJECT_ROOT = Path(__file__).parent.parent
_FOAM_FIXTURE = _PROJECT_ROOT / "tests" / "data" / "foam_case" / "case.foam"


def test_explicit_field_wins_over_available_fields():
    assert _select_field("p", ["U", "p"]) == "p"


def test_defaults_to_first_available_field():
    assert _select_field("", ["Vm", "p"]) == "Vm"


def test_empty_when_no_field_and_no_available_fields():
    assert _select_field("", []) == ""


class _StubMesh:
    def __init__(self, point_data, cell_data):
        self.point_data = point_data
        self.cell_data = cell_data


class _StubSim:
    """Sim whose step-0 mesh carries setup fields absent at later steps."""
    n_steps = 10

    def get_mesh(self, idx):
        if idx == 0:
            return _StubMesh({"conductivity": None, "fiber": None}, {})
        return _StubMesh({"Vm": None}, {"tags": None})


def test_fields_detected_at_rendered_step_not_step_zero():
    # time "mid" of 10 steps = index 5 → the Vm/tags mesh, not the setup mesh
    assert _fields_at_step(_StubSim(), 5) == ["Vm", "tags"]


def test_fields_at_step_empty_when_mesh_missing():
    class _NoMeshSim:
        n_steps = 1

        def get_mesh(self, idx):
            return None

    assert _fields_at_step(_NoMeshSim(), 0) == []


def test_preview_subprocess_adds_html_only_flag_when_requested(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    upload_plugin._run_preview_subprocess(
        tmp_path / "case.vtu", "fig-case", "auto", html_only=True
    )

    assert captured["command"][-1] == "--html-only"


@pytest.mark.skipif(
    not _FOAM_FIXTURE.exists(),
    reason="no committed redistributable .foam fixture yet (CLAUDE.md §6.0)",
)
def test_script_renders_fixture_end_to_end(tmp_path):
    env = {**os.environ, "PROJECT_ROOT": str(tmp_path)}
    proc = subprocess.run(
        [
            sys.executable,
            str(_PROJECT_ROOT / "scripts" / "render_case_preview.py"),
            "--case", str(_FOAM_FIXTURE),
            "--fig-id", "fig-fixture",
            "--decimate", "auto",
        ],
        capture_output=True, text=True, env=env, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    last_line = [l for l in proc.stdout.splitlines() if l.strip()][-1]
    payload = json.loads(last_line)
    assert payload["status"] == "ok"
    assert (tmp_path / "state" / "figures" / "fig-fixture.html").exists()
    assert (tmp_path / "state" / "figures" / "fig-fixture.png").exists()
