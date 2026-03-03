"""Utility helpers for the 4Dpapers dashboard."""
from __future__ import annotations

import importlib.util
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


def load_manifest(manifest_path: Path) -> dict[str, Any] | None:
    """Read plots.json; return parsed dict or None if not found."""
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text())


def resolve_param_paths(params: dict[str, Any], *, root: Path) -> dict[str, Any]:
    """Resolve relative string param values to absolute paths under *root*."""
    resolved: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str) and not Path(value).is_absolute():
            resolved[key] = str(root / value)
        else:
            resolved[key] = value
    return resolved


def load_script_module(module_path: Path, module_name: str = "postproc_script"):
    """Dynamically import a Python file and return the module object."""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_postprocessing_script(
    *,
    module_path: Path,
    function_name: str,
    params: dict[str, Any],
    log_lines: list[str],
) -> Any:
    """
    Import *module_path*, call *function_name*(**params).
    Stdout/stderr are captured into *log_lines* in real-time via a subprocess
    so that the Panel log pane can update incrementally.

    Returns the function's return value (artifact list / dict / None).
    """
    import subprocess
    import threading

    cmd = [
        sys.executable, "-c",
        f"import importlib.util, sys, json\n"
        f"spec = importlib.util.spec_from_file_location('m', {str(module_path)!r})\n"
        f"mod = importlib.util.module_from_spec(spec)\n"
        f"spec.loader.exec_module(mod)\n"
        f"result = mod.{function_name}(**{params!r})\n"
        f"print('__RESULT__:' + json.dumps(result, default=str))\n",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    result_payload = None

    def _read():
        nonlocal result_payload
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("__RESULT__:"):
                result_payload = json.loads(line[len("__RESULT__:"):])
            else:
                log_lines.append(line)

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()
    proc.wait()
    thread.join()

    if proc.returncode != 0:
        log_lines.append(f"[ERROR] Script exited with code {proc.returncode}")

    return result_payload


def run_quarto_render(qmd_path: Path, log_lines: list[str], output_format: str = "html") -> int:
    """
    Run `quarto render <qmd_path> --to <output_format>`.
    Streams output to *log_lines*. Returns the process exit code.
    """
    import os
    import subprocess
    import threading

    env = os.environ.copy()
    env["QUARTO_PYTHON"] = sys.executable
    # Prepend .venv/bin to PATH so the pre-render hook finds the right Python
    venv_bin = str(Path(__file__).parent.parent / ".venv" / "bin")
    env["PATH"] = venv_bin + ":" + env.get("PATH", "")

    proc = subprocess.Popen(
        ["quarto", "render", str(qmd_path), "--to", output_format],
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
    """Serialize PyVista camera state to JSON for use by paraview_render.py."""
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


def run_pvpython_render(
    *,
    pvpython_path: str,
    pvsm_path: str,
    foam_path: str,
    camera_state_path: Path,
    output_path: Path,
    resolution: list[int],
    log_lines: list[str],
) -> int:
    """
    Invoke pvpython to run dashboard/paraview_render.py as a subprocess.
    Streams stdout+stderr to log_lines line by line.
    Returns the process exit code (0 = success).
    """
    import subprocess
    import threading

    render_script = Path(__file__).parent / "paraview_render.py"
    cmd = [
        pvpython_path,
        str(render_script),
        str(pvsm_path),
        str(foam_path),
        str(camera_state_path),
        str(output_path),
        str(resolution[0]),
        str(resolution[1]),
    ]
    log_lines.append(f"[INFO] Running: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def _read_output() -> None:
        for line in proc.stdout:
            log_lines.append(line.rstrip("\n"))

    thread = threading.Thread(target=_read_output, daemon=True)
    thread.start()
    proc.wait()
    thread.join()

    if proc.returncode != 0:
        log_lines.append(
            f"[ERROR] pvpython exited with code {proc.returncode}"
        )
    return proc.returncode
