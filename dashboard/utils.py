"""Utility helpers for the 4Dpapers dashboard."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dashboard.document_signing import sign_html_file_if_configured


def run_quarto_render(
    qmd_path: Path,
    log_lines: list[str],
    output_format: str = "html",
    csl: Path | None = None,
) -> int:
    """Run `quarto render` and stream output to `log_lines`.

    `csl` (optional) is a CSL citation-style file applied via `--metadata csl=`.
    Supported `output_format` values:
      - `html`: dashboard preview HTML (app mode)
      - `html-export`: standalone interactive HTML export
      - `paperview`: static HTML used for PDF preview/export

    Export outputs are named per-paper so preview builds do not overwrite them.
    """
    import os
    import shutil
    import subprocess
    import threading

    # Remove render-local Quarto scratch state before re-rendering. On macOS
    # Docker bind mounts, stale Quarto state has produced two distinct failures:
    #
    # - stale <stem>_files dirs can trigger ensureDirSync/statSync deadlocks
    # - .quarto/project-cache/deno-kv-file can become unreadable/wrong-owner
    #   after mixed root/non-root renders, surfacing as "readonly database"
    #
    # These directories are regenerated on demand, so starting from a clean
    # slate is safer than trying to reuse cross-user cache state.
    _stem = qmd_path.stem
    for _d in (
        qmd_path.parent / f"{_stem}_files",
        qmd_path.parent / "_output" / f"{_stem}_files",
        qmd_path.parent / ".quarto" / "project-cache",
    ):
        try:
            if _d.exists():
                shutil.rmtree(_d, ignore_errors=True)
        except Exception:
            pass

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
    elif output_format == "html-export":
        cmd += ["--output", f"{qmd_path.stem}-standalone.html"]
    elif output_format == "paperview":
        env["FOURD_APP_MODE"] = "1"
        env["FOURD_PAPER_VIEW"] = "1"
        env["FOURD_STRICT_STATIC_EXPORT"] = "1"
        cmd += ["--profile", "paperview"]
        # Per-paper output name (profile no longer hardcodes output-file) so
        # compiling paperII doesn't overwrite paperI's paperview HTML.
        cmd += ["--output", f"{qmd_path.stem}-paperview.html"]
    else:
        cmd = ["quarto", "render", str(qmd_path), "--to", output_format]

    if csl is not None:
        cmd += ["--metadata", f"csl={csl}"]

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
    try:
        proc.wait(timeout=1800)
    except subprocess.TimeoutExpired:
        proc.terminate()
        log_lines.append("CRITICAL ERROR: Quarto render timed out after 1800 seconds.")
        return 1
    thread.join()
    return proc.returncode


def maybe_sign_rendered_html(html_path: Path, log_lines: list[str]) -> bool:
    """Sign a rendered HTML output when signing is configured."""
    if not html_path.exists():
        raise FileNotFoundError(f"Rendered HTML not found: {html_path}")
    if sign_html_file_if_configured(html_path):
        log_lines.append(f"Signed HTML output: {html_path.name}")
        return True
    return False


def save_camera_state(
    position: list[float],
    focal_point: list[float],
    view_up: list[float],
    parallel_scale: float | None,
    parallel_projection: int | None = None,
    *,
    output_path: Path,
) -> bool:
    """Serialize PyVista camera state to JSON.

    Returns True when the on-disk file changed, False when the payload was
    identical and no rewrite was needed.
    """
    payload: dict = {
        "position":    list(position),
        "focal_point": list(focal_point),
        "view_up":     list(view_up),
    }
    if parallel_scale is not None:
        payload["parallel_scale"] = float(parallel_scale)
    if parallel_projection is not None:
        payload["parallel_projection"] = int(parallel_projection)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text())
        except json.JSONDecodeError:
            existing = None
        if existing == payload:
            return False
    output_path.write_text(json.dumps(payload, indent=2))
    return True


def load_camera_state(path: Path) -> dict | None:
    """Load camera JSON or return `None`."""
    if not path.exists():
        return None
    return json.loads(path.read_text())
