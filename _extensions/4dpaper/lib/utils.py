from __future__ import annotations
import sys
import os
from pathlib import Path
from dashboard.document_signing import sign_html_file_if_configured
from .config import _project_root, _app_root, ShortcutResolver, _shortcut_resolver, _shortcuts_yml_path

def _maybe_sign_output_html(output_path: Path) -> None:
    """Apply a trailing signature block when HTML signing is configured."""
    if sign_html_file_if_configured(output_path):
        print(f"Signed HTML: {output_path}", file=sys.stderr)

def resolve_src_path(src_str: str) -> Path:
    """Resolve a source path with optional `@shortcut` syntax."""
    try:
        return _shortcut_resolver.resolve(src_str)
    except ValueError as exc:
        print(f"Warning: {exc}", file=sys.stderr)
        path = Path(src_str)
        return path if path.is_absolute() else _project_root / path

def is_cache_valid(
    fig_path: Path,
    src_path: Path,
    camera_path: Path | None = None,
    field_path: Path | None = None,
    extra_deps: list[Path] | None = None,
) -> bool:
    """Return `True` when the cached figure is newer than its dependencies."""
    if not fig_path.exists():
        return False
    fig_mtime = fig_path.stat().st_mtime
    if src_path.exists() and fig_mtime <= src_path.stat().st_mtime:
        return False
    if camera_path is not None and camera_path.exists():
        if fig_mtime <= camera_path.stat().st_mtime:
            return False
    if field_path is not None and field_path.exists():
        if fig_mtime <= field_path.stat().st_mtime:
            return False
    for dep in (extra_deps or []):
        if dep.exists() and fig_mtime <= dep.stat().st_mtime:
            return False
    return True

