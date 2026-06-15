"""
Dashboard plugin: QMD compile, PDF export, and health-check endpoints.

Routes:
  POST /api/compile  — render the main QMD to HTML (or paperview HTML)
  POST /api/export   — render paperview HTML then convert to PDF via WeasyPrint
  GET  /api/health   — check backend readiness (Quarto present, dirs writable)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import traceback
from pathlib import Path

import tornado.web

from dashboard.auth import SecureMixin
from dashboard.utils import maybe_sign_rendered_html, run_quarto_render
from dashboard.file_plugin import _should_include, _is_write_allowed

# PROJECT_ROOT can be set via environment variable (for Docker) or defaults to parent directory
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))

# Semaphore: only one Quarto render may run at a time to prevent resource exhaustion.
_render_lock = asyncio.Semaphore(1)

# Maximum total body size for the compile endpoint (50 MB across all files).
_MAX_COMPILE_BODY_BYTES = 50 * 1024 * 1024


def _find_main_qmd() -> Path:
    """Find the main QMD file: prefers main.qmd, then analysis_report.qmd,
    then any single .qmd in the project root."""
    for name in ["main.qmd", "analysis_report.qmd"]:
        p = _PROJECT_ROOT / name
        if p.exists():
            return p
    candidates = sorted([f for f in _PROJECT_ROOT.glob("*.qmd") if f.is_file()])
    if candidates:
        return candidates[0]
    return _PROJECT_ROOT / "main.qmd"  # will produce a clear FileNotFoundError


def _resolve_target(body: dict) -> Path:
    """Resolve the paper to compile from the request body's `target`.

    `target` must be a root-level `.qmd` (a paper wrapper) inside the project.
    Falls back to `_find_main_qmd()` when absent or invalid.
    """
    target = (body.get("target") or "").strip()
    if not target:
        return _find_main_qmd()
    # Reject path traversal / nested paths — papers live at the project root.
    if target.endswith(".qmd") and "/" not in target and "\\" not in target and ".." not in target:
        p = (_PROJECT_ROOT / target).resolve()
        try:
            p.relative_to(_PROJECT_ROOT.resolve())
        except ValueError:
            return _find_main_qmd()
        if p.exists() and p.suffix == ".qmd":
            return p
    return _find_main_qmd()


# Citation-style key → CSL file (relative to <project>/_extensions/4dpaper/csl).
# "author-date"/"" use pandoc's built-in default (no CSL file).
_CSL_STYLES = {
    "numeric": "numeric.csl",
}


def _resolve_csl(body: dict) -> "Path | None":
    """Resolve the optional `csl` citation-style key to a CSL file path."""
    style = (body.get("csl") or "").strip().lower()
    fname = _CSL_STYLES.get(style)
    if not fname:
        return None
    p = (_PROJECT_ROOT / "_extensions" / "4dpaper" / "csl" / fname).resolve()
    return p if p.exists() else None


class CompileHandler(SecureMixin, tornado.web.RequestHandler):
    """Compile the main QMD to HTML (interactive) or paperview HTML (static)."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    async def post(self) -> None:
        if not self.check_auth():
            return
        try:
            # Body size guard
            if len(self.request.body) > _MAX_COMPILE_BODY_BYTES:
                self.set_status(413)
                self.write({"error": "Request body exceeds 50 MB limit"})
                return

            body = json.loads(self.request.body)
            files_to_save = body.get("files", {})

            for file_path_str, content in files_to_save.items():
                # Per-file size guard (10 MB)
                if len(content.encode("utf-8", errors="replace")) > 10 * 1024 * 1024:
                    self.set_status(413)
                    self.write({"error": f"File '{file_path_str}' exceeds 10 MB limit"})
                    return

                path = (_PROJECT_ROOT / file_path_str).resolve()
                allowed, reason = _is_write_allowed(_PROJECT_ROOT / file_path_str)
                if not allowed:
                    self.set_status(403)
                    self.write({"error": f"Write denied for '{file_path_str}': {reason}"})
                    return
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                print(f"[CompileHandler] Saved: {path.relative_to(_PROJECT_ROOT)}")

            main_qmd = _resolve_target(body)
            stem = main_qmd.stem
            csl_path = _resolve_csl(body)

            if not main_qmd.exists():
                self.set_status(404)
                self.write({"error": "Main QMD file not found"})
                return

            print(f"[CompileHandler] Starting Quarto render of {main_qmd.name}"
                  f"{f' (csl={csl_path.name})' if csl_path else ''}...")
            log_lines: list[str] = []

            # Frontend sends "pdf" to mean the paperview static profile
            requested_format = body.get("format", "html")
            render_format = "paperview" if requested_format == "pdf" else "html"

            # Run the blocking render in a thread-pool executor; hold the semaphore
            # so only one render runs at a time.
            loop = asyncio.get_event_loop()
            async with _render_lock:
                exit_code = await loop.run_in_executor(
                    None, run_quarto_render, main_qmd, log_lines, render_format, csl_path
                )

            print(f"[CompileHandler] Quarto exit code: {exit_code}")

            if exit_code != 0:
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

            if not html_output.exists():
                self.set_status(500)
                self.write({
                    "error": "Compiled output not found",
                    "log": "\n".join(log_lines[-30:]),
                })
                return

            maybe_sign_rendered_html(html_output, log_lines)

            print(f"[CompileHandler] Successfully compiled: {filename}")
            self.write({
                "status": "success",
                "filename": filename,
                "log": "\n".join(log_lines[-50:]),
            })

        except json.JSONDecodeError as exc:
            self.set_status(400)
            self.write({"error": f"Invalid JSON: {exc}"})
        except Exception as exc:
            self.set_status(500)
            traceback.print_exc()
            self.write({"error": f"{type(exc).__name__}: {str(exc)}"})


class ExportHandler(SecureMixin, tornado.web.RequestHandler):
    """Export the document to PDF via the paperview Quarto profile + WeasyPrint.

    Flow:
      1. Run Quarto with the paperview profile → produces a static HTML where
         every interactive figure is replaced with its saved-camera PNG.
      2. Convert that HTML to PDF using WeasyPrint (pure Python, no LaTeX needed).
      3. Stream the PDF bytes back to the client.
    """

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")

    def options(self) -> None:
        self.finish()

    async def post(self) -> None:
        if not self.check_auth():
            return
        try:
            import weasyprint
        except ImportError:
            self.set_status(500)
            self.set_header("Content-Type", "application/json")
            self.write({"error": "weasyprint is not installed. Run: pip install weasyprint"})
            return

        try:
            try:
                body = json.loads(self.request.body) if self.request.body else {}
            except (ValueError, TypeError):
                body = {}
            main_qmd = _resolve_target(body)
            stem = main_qmd.stem
            csl_path = _resolve_csl(body)

            # Step 1: render paperview HTML (static, figures as saved-camera PNGs)
            log_lines: list[str] = []
            loop = asyncio.get_event_loop()
            async with _render_lock:
                exit_code = await loop.run_in_executor(
                    None, run_quarto_render, main_qmd, log_lines, "paperview", csl_path
                )

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
                self.write({"error": "Paperview HTML not found"})
                return

            maybe_sign_rendered_html(html_path, log_lines)

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
    """Health check — confirms backend is up and key paths are accessible.

    This endpoint is intentionally exempt from authentication so Docker's
    HEALTHCHECK can reach it without credentials.  Sensitive filesystem paths
    are NOT included in the response.
    """

    def set_default_headers(self) -> None:
        # Health check is same-origin only; no CORS needed.
        self.set_header("Content-Type", "application/json")

    def get(self) -> None:
        main_qmd = _find_main_qmd()
        output_dir = _PROJECT_ROOT / "_output"
        state_dir = _PROJECT_ROOT / "state"

        self.write({
            "status": "ok",
            "backend_ready": True,
            "main_qmd": {
                "exists": main_qmd.exists(),
            },
            "output_dir": {
                "exists": output_dir.exists(),
                "writable": output_dir.exists() and os.access(output_dir, os.W_OK),
            },
            "state_dir": {
                "exists": state_dir.exists(),
                "writable": state_dir.exists() and os.access(state_dir, os.W_OK),
            },
        })


ROUTES = [
    (r"/api/compile", CompileHandler),
    (r"/api/export", ExportHandler),
    (r"/api/health", HealthCheckHandler),
]
