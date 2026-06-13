"""Shortcut management endpoints for the dashboard."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import tornado.web
import yaml

_APP_DIR = Path(__file__).parent.parent
_extensions_path = _APP_DIR / "_extensions" / "4dpaper"
if str(_extensions_path) not in sys.path:
    sys.path.insert(0, str(_extensions_path))

from shortcut_resolver import ShortcutResolver

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(_APP_DIR)))

_shortcut_resolver = ShortcutResolver(
    config_path=_PROJECT_ROOT / "_shortcuts.yml",
    project_root=_PROJECT_ROOT
)


class ShortcutsListHandler(tornado.web.RequestHandler):
    """List all defined shortcuts."""

    def get(self) -> None:
        """GET /api/shortcuts — return all shortcuts and descriptions."""
        shortcuts_list = list(_shortcut_resolver.list_shortcuts().keys())
        descriptions = _shortcut_resolver.list_shortcuts()

        self.write({
            "shortcuts": shortcuts_list,
            "descriptions": descriptions,
            "count": len(shortcuts_list)
        })

    def post(self) -> None:
        """POST /api/shortcuts — create or update a shortcut."""
        try:
            data = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            self.write({"error": "Invalid JSON"})
            return

        name = data.get("name", "").strip()
        path = data.get("path", "").strip()
        description = data.get("description", "").strip()

        if not name:
            self.set_status(400)
            self.write({"error": "Missing 'name'"})
            return

        if not _shortcut_resolver._is_valid_shortcut_name(name):
            self.set_status(400)
            self.write({
                "error": "Invalid shortcut name. Must match [a-z0-9_] only."
            })
            return

        if not path:
            self.set_status(400)
            self.write({"error": "Missing 'path'"})
            return

        p = Path(path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p

        if not p.exists():
            self.set_status(400)
            self.write({"error": f"Path does not exist: {p}"})
            return

        config_path = _PROJECT_ROOT / "_shortcuts.yml"
        try:
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}

            if "shortcuts" not in config:
                config["shortcuts"] = {}

            config["shortcuts"][name] = {
                "path": str(p),
                "description": description
            }

            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            _shortcut_resolver._load_config()

            self.write({
                "status": "ok",
                "name": name,
                "path": str(p)
            })
        except Exception as e:
            self.set_status(500)
            self.write({"error": f"Failed to update config: {e}"})


class ShortcutResolveHandler(tornado.web.RequestHandler):
    """Resolve a shortcut reference to its actual path."""

    def get(self) -> None:
        """GET /api/shortcuts/resolve?src=@shortcut_name/path — resolve shortcut."""
        src = self.get_argument("src", default=None)
        if not src:
            self.set_status(400)
            self.write({"error": "Missing 'src' parameter"})
            return

        try:
            resolved = _shortcut_resolver.resolve(src)
            self.write({
                "src": src,
                "resolved": str(resolved),
                "exists": resolved.exists()
            })
        except ValueError as e:
            self.set_status(400)
            self.write({"error": str(e)})


ROUTES = [
    (r"/api/shortcuts$", ShortcutsListHandler),
    (r"/api/shortcuts/resolve", ShortcutResolveHandler),
]
