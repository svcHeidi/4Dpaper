"""Utility helpers for the 4Dpapers dashboard."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

# Resolved at module load; tests can patch this.
CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict[str, Any]:
    """Load and return the dashboard config.yaml."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


def run_quarto_render(qmd_path: Path, log_lines: list[str], output_format: str = "html") -> int:
    """
    Run `quarto render <qmd_path> --to <output_format>`.
    Streams output to *log_lines*. Returns the process exit code.
    """
    import os
    import subprocess
    import threading

    env = os.environ.copy()
    # Always use the project .venv Python for Quarto — it has nbformat/jupyter.
    # sys.executable may point to a different environment (e.g. the system venv
    # used to launch `panel serve`) that lacks those packages.
    _venv_bin = Path(__file__).parent.parent / ".venv" / "bin"
    _venv_python = _venv_bin / "python"
    env["QUARTO_PYTHON"] = str(_venv_python) if _venv_python.exists() else sys.executable
    env["PATH"] = str(_venv_bin) + ":" + env.get("PATH", "")
    # App mode: figures served as static files + embed-resources disabled.
    # embed-resources makes pandoc inline every iframe src (reads & base64s each
    # figure file), which causes 9GB RAM usage and 3-min builds.
    # In the app the HTML is always served locally so standalone is not needed.
    cmd = ["quarto", "render", str(qmd_path), "--to", output_format]
    if output_format == "html":
        env["FOURD_APP_MODE"] = "1"
        cmd += ["--profile", "apphtml"]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(qmd_path.parent),
        env=env,
    )

    def _read():
        for line in proc.stdout:
            log_lines.append(line.rstrip("\n"))

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()
    proc.wait()
    thread.join()
    return proc.returncode


# ── Camera state helpers ──────────────────────────────────────────────────────

def save_camera_state(
    position: list[float],
    focal_point: list[float],
    view_up: list[float],
    parallel_scale: float | None,
    *,
    output_path: Path,
) -> None:
    """Serialize PyVista camera state to JSON."""
    payload: dict = {
        "position":    list(position),
        "focal_point": list(focal_point),
        "view_up":     list(view_up),
    }
    if parallel_scale is not None:
        payload["parallel_scale"] = float(parallel_scale)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))


def load_camera_state(path: Path) -> dict | None:
    """Return camera dict from JSON, or None if file does not exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text())
