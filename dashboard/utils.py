"""Utility helpers for the 4Dpapers dashboard."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


def run_quarto_render(qmd_path: Path, log_lines: list[str], output_format: str = "html") -> int:
    """Run `quarto render` and stream output to `log_lines`."""
    import os
    import subprocess
    import threading

    env = os.environ.copy()
    _venv_bin = Path(__file__).parent.parent / ".venv" / "bin"
    _venv_python = _venv_bin / "python"
    env["QUARTO_PYTHON"] = str(_venv_python) if _venv_python.exists() else sys.executable
    env["PATH"] = "/opt/quarto/bin:" + env.get("PATH", "")

    for qpath in ["/opt/quarto/bin", "/usr/local/bin/quarto", "/Applications/quarto/bin", "/usr/local/bin", "/opt/homebrew/bin"]:
        if qpath not in env.get("PATH", ""):
            env["PATH"] = qpath + ":" + env.get("PATH", "")

    env["PATH"] = str(_venv_bin) + ":" + env.get("PATH", "")

    cmd = ["quarto", "render", str(qmd_path), "--to", "html"]
    if output_format == "html":
        env["FOURD_APP_MODE"] = "1"
        cmd += ["--profile", "apphtml"]
    elif output_format == "paperview":
        env["FOURD_APP_MODE"] = "1"
        env["FOURD_PAPER_VIEW"] = "1"
        cmd += ["--profile", "paperview"]
    else:
        cmd = ["quarto", "render", str(qmd_path), "--to", output_format]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(qmd_path.parent),
            env=env,
        )
    except FileNotFoundError:
        log_lines.append(f"CRITICAL ERROR: 'quarto' executable not found in PATH.")
        log_lines.append(f"PATH checked: {env.get('PATH')}")
        log_lines.append("Please ensure Quarto is installed (https://quarto.org/docs/get-started/)")
        return 127

    def _read():
        for line in proc.stdout:
            log_lines.append(line.rstrip("\n"))

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()
    proc.wait()
    thread.join()
    return proc.returncode


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
    """Load camera JSON or return `None`."""
    if not path.exists():
        return None
    return json.loads(path.read_text())
