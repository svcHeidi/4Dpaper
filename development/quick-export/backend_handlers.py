"""Opt-in Quick Export page and API handlers.

``serve.py`` loads this module only when ``FOURD_QUICK_TARGET`` is set. Normal
dashboard containers therefore do not expose the page or routes. The launcher
provides an isolated project root, a read-only source mount, and a narrow
writable directory used only for retained HTML artifacts.
"""
from __future__ import annotations

import asyncio
import functools
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path

import tornado.web

import dashboard.compile_plugin as compile_core
from dashboard.auth import SecureMixin
from dashboard.render_lock import _render_lock
from dashboard.utils import maybe_sign_rendered_html, run_quarto_render

_DEV_ROOT = Path(__file__).parent
_QUICK_OUTPUT_ENV = "FOURD_QUICK_OUTPUT"


def _resolve_quick_target(project_root: Path) -> Path:
    """Return the configured target after proving it is staged in the workspace."""
    target_str = os.getenv("FOURD_QUICK_TARGET", "").strip()
    if not target_str:
        raise ValueError("Quick Export target is unavailable")

    target = Path(target_str)
    if not target.exists():
        raise ValueError("Quick Export target is unavailable")

    try:
        target.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise ValueError(
            "Quick Export target must be mounted inside its temporary workspace"
        ) from exc
    return target


def _retain_html(source: Path, filename: str) -> Path:
    """Atomically copy one HTML artifact to the launcher's writable output mount."""
    if not source.is_file() or source.suffix.lower() != ".html":
        raise FileNotFoundError(f"HTML artifact not found: {source.name}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.html", filename):
        raise ValueError("Invalid retained HTML filename")

    output_str = os.getenv(_QUICK_OUTPUT_ENV, "").strip()
    if not output_str:
        raise ValueError("Quick Export output directory is not configured")
    output_dir = Path(output_str)
    if not output_dir.is_dir() or not os.access(output_dir, os.W_OK):
        raise PermissionError("Quick Export output directory is not writable")

    destination = output_dir / filename
    temporary = output_dir / f".{filename}.tmp"
    shutil.copyfile(source, temporary)
    temporary.replace(destination)
    return destination


def _shortcode_attribute(name: str, value: str) -> str:
    """Build one parser-safe shortcode attribute or reject ambiguous input."""
    if any(character in value for character in ('"', "'", "\r", "\n")):
        raise ValueError(f"{name} contains unsupported quote or newline characters")
    return f'{name}="{value}"'


def _safe_html_stem(value: str) -> str:
    """Return a portable ASCII filename stem for Content-Disposition."""
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    safe = re.sub(r"[^A-Za-z0-9\s_-]", "", ascii_value)
    return re.sub(r"\s+", "-", safe).strip("-")[:60] or "quick-export"


class QuickPageHandler(tornado.web.StaticFileHandler):
    """Serve the development UI only when this module's routes are registered."""

    def get(self, path: str = "", include_body: bool = True):
        return super().get("quick.html", include_body=include_body)

    def head(self, path: str = ""):
        return self.get(path, include_body=False)


class QuickTargetHandler(SecureMixin, tornado.web.RequestHandler):
    """Return the configured target without exposing the host source path."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def get(self) -> None:
        if not self.check_auth():
            return
        try:
            target = _resolve_quick_target(compile_core._PROJECT_ROOT)
        except ValueError:
            self.write({"target": "", "active": False})
            return
        self.write({"target": target.name, "active": True})


class QuickInitHandler(SecureMixin, tornado.web.RequestHandler):
    """Render a preview for a configured target inside an isolated workspace."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    async def post(self) -> None:
        if not self.check_auth():
            return

        from dashboard.upload_plugin import (
            _parse_preview_stdout,
            _run_preview_subprocess,
            _slugify_fig_id,
        )

        project_root = compile_core._PROJECT_ROOT
        try:
            target = _resolve_quick_target(project_root)
        except ValueError as exc:
            self.set_status(400)
            self.write({"status": "error", "detail": str(exc)})
            return

        fig_id = _slugify_fig_id(target.stem)
        try:
            async with _render_lock:
                loop = asyncio.get_running_loop()
                proc = await loop.run_in_executor(
                    None,
                    functools.partial(
                        _run_preview_subprocess,
                        target,
                        fig_id,
                        "auto",
                        html_only=True,
                    ),
                )
        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            self.set_status(503)
            self.write({"status": "error", "detail": "Render timed out"})
            return

        if proc.returncode != 0:
            self.set_status(500)
            self.write({
                "status": "error",
                "detail": (proc.stderr or "preview render failed").strip()[-2000:],
            })
            return

        result = _parse_preview_stdout(proc.stdout)
        if not result or result.get("status") != "ok":
            self.set_status(500)
            self.write({"status": "error", "detail": "Preview returned invalid status"})
            return

        figure_path = project_root / "state" / "figures" / f"{fig_id}.html"
        try:
            retained_figure = _retain_html(figure_path, f"{fig_id}.html")
        except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
            self.set_status(500)
            self.write({"status": "error", "detail": f"Could not retain figure HTML: {exc}"})
            return

        self.write({
            "status": "ok",
            "fig_id": fig_id,
            "src": target.name,
            "field": result.get("field", ""),
            "fields": result.get("fields", []),
            "retained_figure": retained_figure.name,
        })


class QuickExportHandler(SecureMixin, tornado.web.RequestHandler):
    """Render a standalone HTML document for an initialized figure."""

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")

    def options(self) -> None:
        self.finish()

    async def post(self) -> None:
        if not self.check_auth():
            return

        try:
            body = json.loads(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            self.set_status(400)
            self.write({"error": "Invalid JSON"})
            return

        fig_id = body.get("fig_id", "")
        if not fig_id or not re.fullmatch(r"[A-Za-z0-9_-]+", fig_id):
            self.set_status(400)
            self.write({"error": "Missing or invalid fig_id"})
            return

        project_root = compile_core._PROJECT_ROOT
        try:
            target = _resolve_quick_target(project_root)
        except ValueError as exc:
            self.set_status(400)
            self.write({"error": str(exc)})
            return

        src = target.resolve().relative_to(project_root.resolve()).as_posix()

        title = str(body.get("title") or "").strip()
        author = str(body.get("author") or "").strip()
        description = str(body.get("description") or "").strip()
        field = str(body.get("field") or "").strip()
        fields = body.get("fields") if isinstance(body.get("fields"), list) else []

        clean_fields = [str(value).strip() for value in fields if str(value).strip()]
        try:
            shortcode_parts = [
                _shortcode_attribute("src", src),
                _shortcode_attribute("id", fig_id),
            ]
            if field:
                shortcode_parts.append(_shortcode_attribute("field", field))
            if clean_fields:
                shortcode_parts.append(
                    _shortcode_attribute("fields", ",".join(clean_fields))
                )
        except ValueError as exc:
            self.set_status(400)
            self.write({"error": str(exc)})
            return

        qmd_path = project_root / f"quick-export-{int(time.time() * 1000)}.qmd"
        qmd_parts: list[str] = []
        if title or author:
            qmd_parts.extend(["---"])
            if title:
                qmd_parts.append("title: " + json.dumps(title))
            if author:
                qmd_parts.append("author: " + json.dumps(author))
            qmd_parts.extend(["---", ""])
        if description:
            qmd_parts.extend([description, ""])
        qmd_parts.extend(["{{< 4d-image " + " ".join(shortcode_parts) + " >}}", ""])
        qmd_path.write_text("\n".join(qmd_parts), encoding="utf-8")

        log_lines = compile_core._active_build_log
        log_lines.clear()
        loop = asyncio.get_running_loop()
        try:
            async with _render_lock:
                exit_code = await loop.run_in_executor(
                    None, run_quarto_render, qmd_path, log_lines, "html-export", None
                )
        finally:
            qmd_path.unlink(missing_ok=True)

        if exit_code != 0:
            self.set_status(500)
            self.write({"error": "Quick Export HTML render failed"})
            return

        html_path = project_root / "_output" / f"{qmd_path.stem}-standalone.html"
        if not html_path.exists():
            self.set_status(500)
            self.write({"error": "Quick Export HTML output not found"})
            return

        maybe_sign_rendered_html(html_path, log_lines)
        try:
            compile_core._validate_standalone_html_output(html_path)
        except (FileNotFoundError, ValueError) as exc:
            self.set_status(500)
            self.write({"error": f"Quick Export HTML validation failed: {exc}"})
            return

        safe_name = _safe_html_stem(title or fig_id)
        retained_name = f"{safe_name}-standalone.html"
        try:
            retained_html = _retain_html(html_path, retained_name)
        except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
            self.set_status(500)
            self.write({"error": f"Could not retain standalone HTML: {exc}"})
            return

        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.set_header(
            "Content-Disposition",
            f'attachment; filename="{retained_html.name}"',
        )
        self.set_header("X-4D-Retained-HTML", retained_html.name)
        self.write(html_path.read_bytes())


ROUTES = [
    (r"/quick.html", QuickPageHandler, {"path": str(_DEV_ROOT)}),
    (r"/api/quick-target", QuickTargetHandler),
    (r"/api/quick-init", QuickInitHandler),
    (r"/api/quick-export", QuickExportHandler),
]
