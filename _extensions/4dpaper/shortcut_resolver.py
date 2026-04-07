"""
Shortcut resolver for 4DPapers.

Allows users to define named shortcuts to external data directories
in _shortcuts.yml, then reference them in .qmd shortcodes using @shortcut syntax.

Example config (in _shortcuts.yml):
    shortcuts:
      sim_main:
        path: "/Users/simaocastro/cardiacFoamEP/NiedererEtAl2012"
        description: "Primary simulation case"

Example usage (in .qmd):
    {{< 4d-image src="@sim_main/Niederer.foam" field="Vm" id="fig-vm" >}}
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


class ShortcutResolver:
    """Resolves @shortcut syntax in source paths."""

    def __init__(self, config_path: Path, project_root: Path):
        """
        Initialize the shortcut resolver.

        Args:
            config_path: Path to _shortcuts.yml config file
            project_root: Project root directory (for relative path resolution)
        """
        self.config_path = config_path
        self.project_root = project_root
        self.shortcuts: Dict[str, Path] = {}
        self.descriptions: Dict[str, str] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load and validate shortcut config from YAML."""
        if not self.config_path.exists():
            # No config = no shortcuts available (graceful degradation)
            return

        if yaml is None:
            # PyYAML not available
            return

        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            # Config file corrupted or unreadable (graceful degradation)
            return

        shortcuts_dict = config.get("shortcuts", {})
        if not isinstance(shortcuts_dict, dict):
            return

        for name, info in shortcuts_dict.items():
            # Validate shortcut name: [a-z0-9_] only
            if not self._is_valid_shortcut_name(name):
                continue

            # Extract path and description
            if isinstance(info, dict):
                path_str = info.get("path")
                description = info.get("description", "")
            else:
                # Shorthand syntax: name: /path/to/folder
                path_str = info
                description = ""

            if not path_str:
                continue

            # Resolve relative paths from project root
            path = Path(path_str)
            if not path.is_absolute():
                path = self.project_root / path

            try:
                self.shortcuts[name] = path.resolve()
                self.descriptions[name] = str(description) if description else ""
            except Exception:
                # Path resolution failed (graceful degradation)
                continue

    @staticmethod
    def _is_valid_shortcut_name(name: str) -> bool:
        """Check if shortcut name matches allowed pattern [a-z0-9_]."""
        if not name:
            return False
        return all(c.isalnum() or c == "_" for c in name) and not name[0].isdigit()

    def resolve(self, src: str) -> Path:
        """
        Resolve src path with @shortcut syntax support.

        Syntax:
            - "@shortcut_name/relative/path/to/file" → shortcut base + relative path
            - "@shortcut_name" → shortcut base path
            - "/absolute/path" → used as-is (absolute path)
            - "relative/path" → relative to project root

        Args:
            src: Source path string (may contain @shortcut reference)

        Returns:
            Resolved absolute Path

        Raises:
            ValueError: If shortcut not found or invalid syntax
        """
        if src.startswith("@"):
            # Parse @shortcut/rest/of/path
            parts = src[1:].split("/", 1)
            shortcut_name = parts[0]
            subpath = parts[1] if len(parts) > 1 else ""

            if shortcut_name not in self.shortcuts:
                available = ", ".join(self.shortcuts.keys()) if self.shortcuts else "(none configured)"
                raise ValueError(
                    f"Shortcut '@{shortcut_name}' not found. Available: {available}"
                )

            base = self.shortcuts[shortcut_name]
            if subpath:
                return (base / subpath).resolve()
            else:
                return base

        # Standard path resolution (no @shortcut syntax)
        path = Path(src)
        if not path.is_absolute():
            path = self.project_root / path

        return path.resolve()

    def list_shortcuts(self) -> Dict[str, str]:
        """
        List all defined shortcuts.

        Returns:
            Dict mapping shortcut name → description
        """
        return dict(self.descriptions)

    def get_shortcut(self, name: str) -> Path | None:
        """
        Get the resolved path for a shortcut by name.

        Args:
            name: Shortcut name (without @ prefix)

        Returns:
            Resolved absolute Path, or None if not found
        """
        return self.shortcuts.get(name)
