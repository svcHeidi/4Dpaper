"""
Dashboard plugin: file-tree listing and single-file read/write endpoints.

Routes:
  GET  /api/files        — filtered project file tree (hides system/backend dirs)
  GET  /api/file?path=…  — read a file
  POST /api/file         — write a file
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import tornado.web

# PROJECT_ROOT can be set via environment variable (for Docker) or defaults to parent directory
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))

# Directories hidden from the user-facing file tree (security + noise reduction)
_HIDDEN_DIRS = {
    ".venv", "__pycache__", ".worktrees", ".git", ".github",
    ".quarto", ".pytest_cache", ".cursor", ".superpowers",
    "dashboard", "_extensions", "_freeze", "scripts", "tests",
    "Library",  # macOS
}


def _should_include(path: Path) -> bool:
    """Return True if *path* should appear in the user-facing file tree."""
    if any(skip in path.parts for skip in _HIDDEN_DIRS):
        return False
    if path.name.startswith("."):
        return False
    # Hide state JSON files but keep state/figures/ visible
    if path.parent.name == "state" and path.is_file() and path.suffix == ".json":
        return False
    # Hide Quarto build artifact folders (*_files/)
    if path.is_dir() and path.name.endswith("_files"):
        return False
    if any(part.endswith("_files") for part in path.parts):
        return False
    # Hide compiled HTML at project root (canonical location is _output/)
    if path.parent == _PROJECT_ROOT and path.suffix == ".html":
        return False
    return True


class FilesHandler(tornado.web.RequestHandler):
    """List user-facing files and folders only. Hides backend/system code."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def get(self) -> None:
        try:
            files = []
            for path in _PROJECT_ROOT.rglob("*"):
                if not _should_include(path):
                    continue
                rel_path = str(path.relative_to(_PROJECT_ROOT))
                files.append({
                    "path": rel_path,
                    "is_dir": path.is_dir(),
                    "size": path.stat().st_size if path.is_file() else None,
                    "type": "directory" if path.is_dir() else path.suffix,
                })
            files = sorted(files, key=lambda x: (not x["is_dir"], x["path"]))
            self.write({"files": files, "count": len(files)})
        except Exception as exc:
            self.set_status(500)
            self.write({"error": str(exc)})


class FileHandler(tornado.web.RequestHandler):
    """Read or write a single project file."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.set_header("Content-Type", "text/plain")

    def options(self) -> None:
        self.finish()

    def get(self) -> None:
        try:
            file_path_param = self.get_argument("path", default="")
            if not file_path_param:
                self.set_status(400)
                self.set_header("Content-Type", "application/json")
                self.write({"error": "path parameter required"})
                return

            file_path = _PROJECT_ROOT / file_path_param
            if not file_path.resolve().is_relative_to(_PROJECT_ROOT.resolve()):
                self.set_status(403)
                self.set_header("Content-Type", "application/json")
                self.write({"error": "Access denied"})
                return

            if not file_path.exists():
                self.set_status(404)
                self.set_header("Content-Type", "application/json")
                self.write({"error": "File not found"})
                return

            self.set_header("Content-Type", "text/plain")
            self.write(file_path.read_text(encoding="utf-8"))

        except Exception as exc:
            self.set_status(500)
            self.set_header("Content-Type", "application/json")
            self.write({"error": str(exc)})

    async def post(self) -> None:
        try:
            self.set_header("Content-Type", "application/json")
            body = json.loads(self.request.body)
            file_path_param = body.get("path", "")
            content = body.get("content", "")

            if not file_path_param:
                self.set_status(400)
                self.write({"error": "path required"})
                return

            file_path = _PROJECT_ROOT / file_path_param
            if not file_path.resolve().is_relative_to(_PROJECT_ROOT.resolve()):
                self.set_status(403)
                self.write({"error": "Access denied"})
                return

            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            self.write({"status": "saved", "path": file_path_param})

        except Exception as exc:
            self.set_status(500)
            self.write({"error": str(exc)})


ROUTES = [
    (r"/api/files", FilesHandler),
    (r"/api/file", FileHandler),
]
