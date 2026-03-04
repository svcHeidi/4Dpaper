"""
Project file tree sidebar for the 4Dpapers dashboard.

Provides an Overleaf-style file browser showing the full project directory.
Clicking an editable file opens it in the code editor.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

HIDDEN_DIRS = {
    ".git", ".venv", "__pycache__", "_freeze", ".quarto",
    "node_modules", ".claude", ".pytest_cache", ".ipynb_checkpoints",
}

EDITABLE_EXTENSIONS = {
    ".qmd", ".bib", ".yaml", ".yml", ".css", ".tex", ".md", ".txt",
}

LANGUAGE_MAP = {
    ".qmd": "markdown",
    ".md": "markdown",
    ".txt": "text",
    ".bib": "latex",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".css": "css",
    ".tex": "latex",
}


def is_editable(filename: str) -> bool:
    """Return True if the file extension is in the editable set."""
    return Path(filename).suffix.lower() in EDITABLE_EXTENSIONS


def list_project_files(directory: Path) -> list[dict[str, Any]]:
    """
    List files and directories in *directory*, excluding hidden/build dirs.

    Returns a list of dicts with keys: name, path, is_dir, editable.
    Sorted: directories first (alphabetically), then files (alphabetically).
    """
    if not directory.is_dir():
        return []

    dirs = []
    files = []
    for item in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if item.name.startswith(".") and item.name in HIDDEN_DIRS:
            continue
        if item.is_dir():
            if item.name in HIDDEN_DIRS:
                continue
            dirs.append({
                "name": item.name,
                "path": str(item),
                "is_dir": True,
                "editable": False,
            })
        else:
            files.append({
                "name": item.name,
                "path": str(item),
                "is_dir": False,
                "editable": is_editable(item.name),
            })

    return dirs + files


def get_language(filename: str) -> str:
    """Return the CodeEditor language mode for a filename."""
    suffix = Path(filename).suffix.lower()
    return LANGUAGE_MAP.get(suffix, "text")
