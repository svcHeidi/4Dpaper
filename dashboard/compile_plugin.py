"""
Dashboard plugin: QMD compile, PDF export, and health-check endpoints.

Routes:
  POST /api/compile  — render the main QMD to HTML (or paperview HTML)
  POST /api/export   — render paperview HTML then convert to PDF via WeasyPrint
  GET  /api/health   — check backend readiness (Quarto present, dirs writable)
"""
from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path

import tornado.web

from dashboard.utils import run_quarto_render

# PROJECT_ROOT can be set via environment variable (for Docker) or defaults to parent directory
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))


def _find_main_qmd() -> Path:
    """Find the main QMD file: prefers main.qmd, then analysis_report.qmd,
    then any single .qmd in the project root."""
    for name in ["main.qmd", "analysis_report.qmd"]:
        p = _PROJECT_ROOT / name
        if p.exists():
            return p
    candidates = [f for f in _PROJECT_ROOT.glob("*.qmd") if f.is_file()]
    if candidates:
        return candidates[0]
    return _PROJECT_ROOT / "main.qmd"  # will produce a clear FileNotFoundError


class CompileHandler(tornado.web.RequestHandler):
    """Compile the main QMD to HTML (interactive) or paperview HTML (static)."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def post(self) -> None:
        try:
            body = json.loads(self.request.body)
            files_to_save = body.get("files", {})

            for file_path, content in files_to_save.items():
                path = _PROJECT_ROOT / file_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                print(f"[CompileHandler] Saved: {path}")

            main_qmd = _find_main_qmd()
            stem = main_qmd.stem
            print(f"[CompileHandler] Main QMD: {main_qmd}")
            print(f"[CompileHandler] Exists: {main_qmd.exists()}")

            if not main_qmd.exists():
                self.set_status(404)
                self.write({
                    "error": f"Main QMD file not found at {main_qmd}",
                    "path_checked": str(main_qmd),
                })
                return

            print("[CompileHandler] Starting Quarto render...")
            log_lines: list[str] = []

            # Frontend sends "pdf" to mean the paperview static profile
            requested_format = body.get("format", "html")
            render_format = "paperview" if requested_format == "pdf" else "html"

            exit_code = run_quarto_render(main_qmd, log_lines, output_format=render_format)
            print(f"[CompileHandler] Quarto exit code: {exit_code}")
            print(f"[CompileHandler] Log lines: {len(log_lines)}")

            if exit_code != 0:
                print("[CompileHandler] Render failed. Last 50 lines:")
                for line in log_lines[-50:]:
                    print(f"  {line}")
                self.set_status(500)
                self.write({
                    "error": "Compilation failed",
                    "exit_code": exit_code,
                    "log": "\n".join(log_lines[-50:]),
                })
                return

            filename = f"{stem}-paperview.html" if render_format == "paperview" else f"{stem}.html"
            html_output = _PROJECT_ROOT / "_output" / filename

            # Wait up to 3 s for Quarto to finish flushing the file
            for _ in range(6):
                if html_output.exists():
                    break
                time.sleep(0.5)

            print(f"[CompileHandler] Looking for output: {html_output}")
            print(f"[CompileHandler] Output exists: {html_output.exists()}")

            if not html_output.exists():
                output_dir = _PROJECT_ROOT / "_output"
                found = list(output_dir.glob("*")) if output_dir.exists() else []
                self.set_status(500)
                self.write({
                    "error": f"Compiled output not found at {html_output}",
                    "project_root": str(_PROJECT_ROOT),
                    "path_checked": str(html_output),
                    "output_dir_contents": [str(f) for f in found],
                    "log": "\n".join(log_lines[-30:]),
                })
                return

            print(f"[CompileHandler] Successfully compiled: {filename}")
            self.write({
                "status": "success",
                "filename": filename,
                "log": "\n".join(log_lines[-50:]),
            })

        except json.JSONDecodeError as exc:
            self.set_status(400)
            print(f"[CompileHandler] JSON error: {exc}")
            self.write({"error": f"Invalid JSON: {exc}"})
        except Exception as exc:
            self.set_status(500)
            print(f"[CompileHandler] Unexpected error: {exc}")
            traceback.print_exc()
            self.write({"error": f"{type(exc).__name__}: {str(exc)}"})


class ExportHandler(tornado.web.RequestHandler):
    """Export the document to PDF via the paperview Quarto profile + WeasyPrint.

    Flow:
      1. Run Quarto with the paperview profile → produces a static HTML where
         every interactive figure is replaced with its saved-camera PNG.
      2. Convert that HTML to PDF using WeasyPrint (pure Python, no LaTeX needed).
      3. Stream the PDF bytes back to the client.
    """

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")

    def options(self) -> None:
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.finish()

    def post(self) -> None:
        try:
            import weasyprint
        except ImportError:
            self.set_status(500)
            self.set_header("Content-Type", "application/json")
            self.write({"error": "weasyprint is not installed. Run: pip install weasyprint"})
            return

        try:
            main_qmd = _find_main_qmd()
            stem = main_qmd.stem

            # Step 1: render paperview HTML (static, figures as saved-camera PNGs)
            log_lines: list[str] = []
            exit_code = run_quarto_render(main_qmd, log_lines, output_format="paperview")

            if exit_code != 0:
                self.set_status(500)
                self.set_header("Content-Type", "application/json")
                self.write({
                    "error": "Paperview render failed",
                    "log": "\n".join(log_lines[-50:]),
                })
                return

            html_path = _PROJECT_ROOT / "_output" / f"{stem}-paperview.html"
            if not html_path.exists():
                self.set_status(500)
                self.set_header("Content-Type", "application/json")
                self.write({"error": f"Paperview HTML not found at {html_path}"})
                return

            # Step 2: HTML → PDF (base_url resolves relative image paths)
            pdf_bytes = weasyprint.HTML(
                filename=str(html_path),
                base_url=str(html_path.parent),
            ).write_pdf()

            # Step 3: stream to client
            self.set_header("Content-Type", "application/pdf")
            self.set_header("Content-Disposition", f'attachment; filename="{stem}.pdf"')
            self.write(pdf_bytes)

        except Exception as exc:
            self.set_status(500)
            self.set_header("Content-Type", "application/json")
            traceback.print_exc()
            self.write({"error": f"{type(exc).__name__}: {str(exc)}"})


class HealthCheckHandler(tornado.web.RequestHandler):
    """Health check — confirms backend is up and key paths are accessible."""

    def set_default_headers(self) -> None:
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")

    def get(self) -> None:
        main_qmd = _find_main_qmd()
        output_dir = _PROJECT_ROOT / "_output"
        state_dir = _PROJECT_ROOT / "state"

        self.write({
            "status": "ok",
            "backend_ready": True,
            "project_root": str(_PROJECT_ROOT),
            "main_qmd": {
                "path": str(main_qmd),
                "exists": main_qmd.exists(),
            },
            "output_dir": {
                "path": str(output_dir),
                "exists": output_dir.exists(),
                "writable": output_dir.exists() and os.access(output_dir, os.W_OK),
            },
            "state_dir": {
                "path": str(state_dir),
                "exists": state_dir.exists(),
                "writable": state_dir.exists() and os.access(state_dir, os.W_OK),
            },
        })


ROUTES = [
    (r"/api/compile", CompileHandler),
    (r"/api/export", ExportHandler),
    (r"/api/health", HealthCheckHandler),
]
