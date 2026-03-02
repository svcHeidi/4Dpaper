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


def run_quarto_render(qmd_path: Path, log_lines: list[str]) -> int:
    """
    Run `quarto render <qmd_path>`.  Streams output to *log_lines*.
    Returns the process exit code.
    """
    import os
    import subprocess
    import threading

    # Tell Quarto to use the same Python that is running this dashboard,
    # so it picks up jupyter/nbformat from the active venv.
    env = os.environ.copy()
    env["QUARTO_PYTHON"] = sys.executable

    proc = subprocess.Popen(
        ["quarto", "render", str(qmd_path)],
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
