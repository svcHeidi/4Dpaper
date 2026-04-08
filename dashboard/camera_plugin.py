"""
Panel plugin: per-figure camera state sync endpoint.

Add to panel serve with:
    panel serve dashboard/app.py --plugins dashboard.camera_plugin ...

Panel reads the ROUTES list and registers the handlers with Tornado.
The srcdoc iframe has a null origin, so CORS headers allow all origins.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import tornado.web

from dashboard.utils import save_camera_state, run_quarto_render

# PROJECT_ROOT can be set via environment variable (for Docker) or defaults to parent directory
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))
_SAFE_FIG_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _find_main_qmd() -> Path:
    """Find the main QMD file: prefers main.qmd, falls back to analysis_report.qmd,
    then any single .qmd in the project root."""
    for name in ["main.qmd", "analysis_report.qmd"]:
        p = _PROJECT_ROOT / name
        if p.exists():
            return p
    candidates = [f for f in _PROJECT_ROOT.glob("*.qmd") if f.is_file()]
    if candidates:
        return candidates[0]
    return _PROJECT_ROOT / "main.qmd"  # will fail with a clear error


class CameraHandler(tornado.web.RequestHandler):
    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def post(self, fig_id: str) -> None:
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400)
            self.write({"status": "error", "detail": "invalid fig_id"})
            return
        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError as exc:
            self.set_status(400)
            self.write({"status": "error", "detail": f"invalid JSON: {exc}"})
            return
        missing = [k for k in ("position", "focal_point", "view_up") if k not in body]
        if missing:
            self.set_status(400)
            self.write({"status": "error", "detail": f"missing keys: {missing}"})
            return
        cam_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}.json"
        save_camera_state(
            position=body["position"],
            focal_point=body["focal_point"],
            view_up=body["view_up"],
            parallel_scale=body.get("parallel_scale"),
            output_path=cam_path,
        )
        self.write({"status": "ok"})


class CameraLockHandler(tornado.web.RequestHandler):
    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self, fig_id: str) -> None:
        self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def get(self, fig_id: str) -> None:
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400)
            self.write({"status": "error"})
            return
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        if lock_path.exists():
            self.write(json.loads(lock_path.read_text()))
        else:
            self.write({"locked": False})

    def post(self, fig_id: str) -> None:
        if not _SAFE_FIG_ID.fullmatch(fig_id):
            self.set_status(400)
            self.write({"status": "error"})
            return
        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError as exc:
            self.set_status(400)
            self.write({"status": "error", "detail": f"invalid JSON: {exc}"})
            return
        lock_path = _PROJECT_ROOT / "state" / f"camera_{fig_id}_lock.json"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps({"locked": bool(body.get("locked", False))}))
        self.write({"status": "ok"})


# ── API Endpoints for Frontend ──────────────────────────────────────────────────

class FilesHandler(tornado.web.RequestHandler):
    """List user-facing files and folders only. Hide backend/system code (security)."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def get(self) -> None:
        """Return file/folder tree for user-facing content only."""
        try:
            files = []

            # HIDE: System/backend code directories (security)
            HIDDEN_DIRS = {
                ".venv", "__pycache__", ".worktrees", ".git", ".github",
                ".quarto", ".pytest_cache", ".cursor", ".superpowers",
                "dashboard", "_extensions", "_freeze", "scripts", "tests",
                "Library"  # macOS
            }

            def should_include(path):
                # Skip hidden system directories
                if any(skip in path.parts for skip in HIDDEN_DIRS):
                    return False
                # Skip dotfiles
                if path.name.startswith('.'):
                    return False
                # Hide state JSON files (camera_*.json, field_*.json)
                # but keep state/figures/ folder visible
                if path.parent.name == "state" and path.is_file():
                    if path.suffix == ".json":
                        return False
                # Hide Quarto build artifact folders (*_files/)
                if path.is_dir() and path.name.endswith("_files"):
                    return False
                if any(part.endswith("_files") for part in path.parts):
                    return False
                # Hide compiled HTML at project root (goes to _output/)
                if path.parent == _PROJECT_ROOT and path.suffix == ".html":
                    return False
                return True

            # Get all files recursively, with filtering
            for path in _PROJECT_ROOT.rglob("*"):
                if not should_include(path):
                    continue

                rel_path = str(path.relative_to(_PROJECT_ROOT))
                files.append({
                    "path": rel_path,
                    "is_dir": path.is_dir(),
                    "size": path.stat().st_size if path.is_file() else None,
                    "type": "directory" if path.is_dir() else path.suffix
                })

            files = sorted(files, key=lambda x: (not x["is_dir"], x["path"]))
            self.write({"files": files, "count": len(files)})
        except Exception as e:
            self.set_status(500)
            self.write({"error": str(e)})


class FileHandler(tornado.web.RequestHandler):
    """Read a single file."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "text/plain")

    def get(self) -> None:
        """Return file content."""
        try:
            file_path_param = self.get_argument("path", default="")
            if not file_path_param:
                self.set_status(400)
                self.set_header("Content-Type", "application/json")
                self.write({"error": "path parameter required"})
                return

            file_path = _PROJECT_ROOT / file_path_param

            # Security: prevent directory traversal
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

            content = file_path.read_text(encoding="utf-8")
            self.set_header("Content-Type", "text/plain")
            self.write(content)

        except Exception as e:
            self.set_status(500)
            self.set_header("Content-Type", "application/json")
            self.write({"error": str(e)})

    async def post(self) -> None:
        """Save file content."""
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

        except Exception as e:
            self.set_status(500)
            self.write({"error": str(e)})


class CompileHandler(tornado.web.RequestHandler):
    """Compile QMD to HTML."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def post(self) -> None:
        """Compile the main QMD file."""
        try:
            # Save files from frontend
            body = json.loads(self.request.body)
            files_to_save = body.get("files", {})

            for file_path, content in files_to_save.items():
                path = _PROJECT_ROOT / file_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                print(f"[CompileHandler] Saved: {path}")

            # Render main document
            main_qmd = _find_main_qmd()
            stem = main_qmd.stem
            print(f"[CompileHandler] Main QMD: {main_qmd}")
            print(f"[CompileHandler] Exists: {main_qmd.exists()}")

            if not main_qmd.exists():
                self.set_status(404)
                self.write({
                    "error": f"Main QMD file not found at {main_qmd}",
                    "path_checked": str(main_qmd)
                })
                return

            print(f"[CompileHandler] Starting Quarto render...")
            log_lines = []

            # Map 'pdf' from frontend to 'paperview' for rendering
            requested_format = body.get("format", "html")
            render_format = "paperview" if requested_format == "pdf" else "html"

            exit_code = run_quarto_render(main_qmd, log_lines, output_format=render_format)
            print(f"[CompileHandler] Quarto exit code: {exit_code}")
            print(f"[CompileHandler] Log lines: {len(log_lines)}")

            if exit_code != 0:
                print(f"[CompileHandler] Render failed. Last 50 lines:")
                for line in log_lines[-50:]:
                    print(f"  {line}")
                self.set_status(500)
                self.write({
                    "error": "Compilation failed",
                    "exit_code": exit_code,
                    "log": "\n".join(log_lines[-50:])
                })
                return

            # Output filename is derived from the QMD stem
            filename = f"{stem}-paperview.html" if render_format == "paperview" else f"{stem}.html"
            
            html_output = _PROJECT_ROOT / "_output" / filename
            print(f"[CompileHandler] Looking for output: {html_output}")
            print(f"[CompileHandler] Output exists: {html_output.exists()}")

            if not html_output.exists():
                # List what IS in _output for debugging
                output_dir = _PROJECT_ROOT / "_output"
                found = list(output_dir.glob("*")) if output_dir.exists() else []
                self.set_status(500)
                self.write({
                    "error": f"Compiled output not found at {html_output}",
                    "path_checked": str(html_output),
                    "output_dir_contents": [str(f) for f in found],
                    "log": "\n".join(log_lines[-30:])
                })
                return

            print(f"[CompileHandler] Successfully compiled: {filename}")
            self.write({
                "status": "success",
                "filename": filename,
                "log": "\n".join(log_lines[-50:]),
            })

        except json.JSONDecodeError as e:
            self.set_status(400)
            print(f"[CompileHandler] JSON error: {e}")
            self.write({"error": f"Invalid JSON: {e}"})
        except Exception as e:
            self.set_status(500)
            print(f"[CompileHandler] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            self.write({"error": f"{type(e).__name__}: {str(e)}"})


class ExportHandler(tornado.web.RequestHandler):
    """Export to PDF."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")

    def options(self) -> None:
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def post(self) -> None:
        """Export compiled document to PDF."""
        try:
            main_qmd = _find_main_qmd()
            stem = main_qmd.stem

            log_lines = []
            exit_code = run_quarto_render(main_qmd, log_lines, output_format="pdf")

            if exit_code != 0:
                self.set_status(500)
                self.set_header("Content-Type", "application/json")
                self.write({
                    "error": "PDF export failed",
                    "log": "\n".join(log_lines[-50:])
                })
                return

            pdf_output = _PROJECT_ROOT / "_output" / f"{stem}.pdf"
            if not pdf_output.exists():
                self.set_status(500)
                self.set_header("Content-Type", "application/json")
                self.write({"error": "PDF output not found"})
                return

            pdf_content = pdf_output.read_bytes()
            self.set_header("Content-Type", "application/pdf")
            self.set_header("Content-Disposition", f'attachment; filename="{stem}.pdf"')
            self.write(pdf_content)

        except Exception as e:
            self.set_status(500)
            self.set_header("Content-Type", "application/json")
            self.write({"error": str(e)})


class HealthCheckHandler(tornado.web.RequestHandler):
    """Health check endpoint to verify backend is ready."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def get(self) -> None:
        """Check if backend is ready to compile."""
        main_qmd = _find_main_qmd()
        output_dir = _PROJECT_ROOT / "_output"
        state_dir = _PROJECT_ROOT / "state"

        self.write({
            "status": "ok",
            "backend_ready": True,
            "project_root": str(_PROJECT_ROOT),
            "main_qmd": {
                "path": str(main_qmd),
                "exists": main_qmd.exists()
            },
            "output_dir": {
                "path": str(output_dir),
                "exists": output_dir.exists(),
                "writable": output_dir.exists() and os.access(output_dir, os.W_OK)
            },
            "state_dir": {
                "path": str(state_dir),
                "exists": state_dir.exists(),
                "writable": state_dir.exists() and os.access(state_dir, os.W_OK)
            }
        })


ROUTES = [
    (r"/camera/(?P<fig_id>[^/]+)", CameraHandler),
    (r"/camera-lock/(?P<fig_id>[^/]+)", CameraLockHandler),
    (r"/api/files", FilesHandler),
    (r"/api/file", FileHandler),
    (r"/api/compile", CompileHandler),
    (r"/api/export", ExportHandler),
    (r"/api/health", HealthCheckHandler),
]
