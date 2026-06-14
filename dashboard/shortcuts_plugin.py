"""Shortcut management endpoints for the dashboard."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import tornado.web
import yaml

from dashboard.auth import SecureMixin

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

# Shortcut names must match [a-z0-9_] (enforced by ShortcutResolver._is_valid_shortcut_name)
_SAFE_NAME = re.compile(r"^[a-z0-9_]+$")


class ShortcutsListHandler(SecureMixin, tornado.web.RequestHandler):
    """List all defined shortcuts."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def get(self) -> None:
        """GET /api/shortcuts — return all shortcuts and descriptions."""
        if not self.check_auth():
            return
        shortcuts_list = list(_shortcut_resolver.list_shortcuts().keys())
        descriptions = _shortcut_resolver.list_shortcuts()

        self.write({
            "shortcuts": shortcuts_list,
            "descriptions": descriptions,
            "count": len(shortcuts_list)
        })

    def post(self) -> None:
        """POST /api/shortcuts — create or update a shortcut."""
        if not self.check_auth():
            return
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
            self.write({"error": "Path does not exist"})  # don't echo the path back
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
                # Return relative path if inside project root; absolute otherwise
                "path": str(p.relative_to(_PROJECT_ROOT)) if p.is_relative_to(_PROJECT_ROOT) else str(p),
            })
        except Exception:
            self.set_status(500)
            self.write({"error": "Failed to update shortcut config"})


class ShortcutCheckHandler(SecureMixin, tornado.web.RequestHandler):
    """Check whether a path exists on the server (for live validation)."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def get(self) -> None:
        """GET /api/shortcuts/check?path=<abs> — validate a candidate shortcut path."""
        if not self.check_auth():
            return
        path_str = self.get_argument("path", default=None)
        if not path_str:
            self.set_status(400)
            self.write({"error": "Missing 'path' parameter"})
            return

        p = Path(path_str)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p

        self.write({"exists": p.exists(), "resolved": str(p)})


class ShortcutResolveHandler(SecureMixin, tornado.web.RequestHandler):
    """Resolve a shortcut reference to its actual path."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def get(self) -> None:
        """GET /api/shortcuts/resolve?src=@shortcut_name/path — resolve shortcut."""
        if not self.check_auth():
            return
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


class ShortcutDeleteHandler(SecureMixin, tornado.web.RequestHandler):
    """Delete a shortcut by name."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="DELETE, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self, name: str) -> None:
        self.finish()

    def delete(self, name: str) -> None:
        if not self.check_auth():
            return
        if not _SAFE_NAME.fullmatch(name):
            self.set_status(400)
            self.write({"error": "Invalid shortcut name"})
            return

        config_path = _PROJECT_ROOT / "_shortcuts.yml"
        try:
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}

            shortcuts = config.get("shortcuts", {})
            if name not in shortcuts:
                self.set_status(404)
                self.write({"error": f"Shortcut '{name}' not found"})
                return

            del shortcuts[name]
            config["shortcuts"] = shortcuts

            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            _shortcut_resolver._load_config()
            self.write({"status": "ok", "deleted": name})
        except Exception:
            self.set_status(500)
            self.write({"error": "Failed to delete shortcut"})


ROUTES = [
    (r"/api/shortcuts$", ShortcutsListHandler),
    (r"/api/shortcuts/check", ShortcutCheckHandler),
    (r"/api/shortcuts/resolve", ShortcutResolveHandler),
    (r"/api/shortcuts/([a-z0-9_]+)", ShortcutDeleteHandler),
]
