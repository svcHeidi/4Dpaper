"""Stage uploaded files and return default shortcodes."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

import tornado.web

from dashboard.auth import SecureMixin
from dashboard.render_lock import _render_lock

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))
_UPLOAD_ROOT = _PROJECT_ROOT / "state" / "upload_tmp"

# Standalone render script invoked as a subprocess on figure upload.
_PREVIEW_SCRIPT = Path(__file__).parent.parent / "scripts" / "render_case_preview.py"

# Budget for one preview render (HTML + PNG) of an uploaded case. A real
# 158-timestep cardiac case measured ~90s on an M-series laptop, so 120s was
# too tight.
_PREVIEW_TIMEOUT_S = 300

# Budget for acquiring the shared render lock: an in-flight Quarto compile can
# hold it for up to 1800s, and the upload request must not hang behind it.
_LOCK_ACQUIRE_TIMEOUT_S = 15

# upload_id must be a safe alphanumeric token (prevents staging-dir injection).
_SAFE_UPLOAD_ID = re.compile(r"^[A-Za-z0-9_-]{4,128}$")

# Maximum bytes allowed for a single uploaded file (5 GB).
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024

# Permitted extensions for uploaded simulation data files.
_ALLOWED_UPLOAD_EXTENSIONS = frozenset({
    ".foam", ".openfoam",
    ".vtu", ".vtp", ".vtk", ".pvd",
    ".stl", ".obj", ".ply",
    ".case",
    ".cgns",
    ".exo", ".e", ".ex2",
    ".xdmf", ".xmf", ".h5", ".hdf5",
    ".json",    # vtk.series + Plotly JSON
    ".series",
    ".bib", ".qmd", ".md", ".csv", ".txt",  # generic file-mode uploads
})

_OPENFOAM_ONLY_FIGURE_ERROR = (
    "Figure upload currently supports OpenFOAM case folders only. "
    "No .foam file was found in the dropped folder."
)
_RAW_H5_UPLOAD_ERROR = (
    "Generic .h5 uploads are not supported. Use .hdf5 for generic HDF5 data, "
    "or upload .h5 only as a companion file alongside an .xdmf or .xmf dataset."
)


def generate_shortcode(
    *,
    src: str,
    field: str,
    fig_id: str,
    time: str,
    caption: str,
    fields: list[str] | None = None,
) -> str:
    """Build a default `4d-image` shortcode."""
    parts = [f'src="{src}"', f'field="{field}"', f'id="{fig_id}"']
    if fields and len(fields) > 1:
        # Persist the live field switcher across full Quarto recompiles.
        parts.append('fields="' + ",".join(fields) + '"')
    if time and time != "mid":
        parts.append(f'time="{time}"')
    if caption.strip():
        parts.append(f'caption="{caption.strip()}"')
    return "{{< 4d-image " + " ".join(parts) + " >}}"


def _slugify_fig_id(case_name: str) -> str:
    """Derive a figure id matching the shortcode id charset `[A-Za-z0-9_-]+`."""
    slug = re.sub(r"[^a-z0-9_-]+", "-", case_name.lower()).strip("-")
    return f"fig-{slug}" if slug else "fig-case"


def _preview_python() -> str:
    """Interpreter for the preview subprocess.

    Prefers the project venv (mirroring the re-exec in 4dpaper.py) so preview
    and Quarto compile render with the same library versions.
    """
    venv_python = _PROJECT_ROOT / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def _run_preview_subprocess(
    case_path: Path,
    fig_id: str,
    decimate: str,
    *,
    html_only: bool = False,
) -> subprocess.CompletedProcess:
    """Render the HTML + PNG preview for one case in a subprocess."""
    command = [
        _preview_python(), str(_PREVIEW_SCRIPT),
        "--case", str(case_path),
        "--fig-id", fig_id,
        "--decimate", decimate,
    ]
    if html_only:
        command.append("--html-only")
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=_PREVIEW_TIMEOUT_S,
    )


def _parse_preview_stdout(stdout: str) -> dict | None:
    """Parse the JSON status line (last non-empty stdout line) or `None`."""
    for line in reversed((stdout or "").splitlines()):
        if not line.strip():
            continue
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            return None
        return result if isinstance(result, dict) else None
    return None


def create_case_symlink(
    foam_path: Path,
    dest_data_dir: Path,
    log_lines: list[str]
) -> Path:
    """Symlink a case directory into `data/` and fall back to copy on failure."""
    case_root = foam_path.parent
    case_name = case_root.name
    dest_case = dest_data_dir / case_name
    upload_root_resolved = _UPLOAD_ROOT.resolve()
    case_root_resolved = case_root.resolve()

    if dest_case.exists() or dest_case.is_symlink():
        if dest_case.is_symlink():
            dest_case.unlink()
        else:
            shutil.rmtree(dest_case)

    # Cases staged under upload_tmp cannot be symlinked directly because the
    # staging directory is deleted after /upload/finish completes.
    if upload_root_resolved == case_root_resolved or upload_root_resolved in case_root_resolved.parents:
        log_lines.append("  Staged upload detected; copying case data into data/")
        return copy_case_data(foam_path, dest_data_dir, log_lines)

    try:
        dest_case.parent.mkdir(parents=True, exist_ok=True)
        dest_case.symlink_to(case_root)
        log_lines.append(f"  Symlinked {case_root.name} → data/{case_name}")
        return dest_case / foam_path.name
    except (OSError, NotImplementedError) as e:
        log_lines.append(f"  Symlink failed ({e}), falling back to copy")
        return copy_case_data(foam_path, dest_data_dir, log_lines)


def copy_case_data(foam_path: Path, dest_data_dir: Path, log_lines: list[str]) -> Path:
    """Copy the case files required for PyVista rendering."""
    case_root = foam_path.parent
    case_name = case_root.name
    dest_case = dest_data_dir / case_name
    dest_case.mkdir(parents=True, exist_ok=True)

    dest_foam = dest_case / foam_path.name
    shutil.copy2(foam_path, dest_foam)
    log_lines.append(f"  Copied {foam_path.name}")

    serial_mesh = case_root / "constant" / "polyMesh"
    if serial_mesh.exists():
        dst = dest_case / "constant" / "polyMesh"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(serial_mesh, dst)
        log_lines.append("  Copied constant/polyMesh/")

    # The VTK OpenFOAM reader expects system/controlDict to be present.
    system_dir = case_root / "system"
    if system_dir.exists():
        dst = dest_case / "system"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(system_dir, dst)
        log_lines.append("  Copied system/")

    # Serial (reconstructed) cases keep results in numeric time dirs at the
    # case root — without them the case loads with zero time steps.
    for item in case_root.iterdir():
        if not item.is_dir():
            continue
        try:
            float(item.name)
        except ValueError:
            continue
        dst = dest_case / item.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(item, dst)
        log_lines.append(f"  Copied {item.name}/")

    for proc_dir in sorted(case_root.glob("processor*")):
        if not proc_dir.is_dir():
            continue
        dest_proc = dest_case / proc_dir.name
        dest_proc.mkdir(exist_ok=True)

        proc_mesh = proc_dir / "constant" / "polyMesh"
        if proc_mesh.exists():
            dst = dest_proc / "constant" / "polyMesh"
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(proc_mesh, dst)

        for item in proc_dir.iterdir():
            if not item.is_dir():
                continue
            try:
                float(item.name)
            except ValueError:
                continue
            dst = dest_proc / item.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)

        log_lines.append(f"  Copied {proc_dir.name}/")

    return dest_foam


def _safe_rel_path(rel_path: str) -> Path | None:
    """Return a safe relative path or `None`."""
    try:
        p = Path(rel_path)
    except Exception:
        return None

    if p.is_absolute():
        return None

    parts = list(p.parts)
    if any(part in ("..", "") for part in parts):
        return None

    if parts and len(parts[0]) == 2 and parts[0][1] == ":":
        return None

    return Path(*parts)


@tornado.web.stream_request_body
class UploadFileHandler(SecureMixin, tornado.web.RequestHandler):

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def prepare(self) -> None:
        # Auth check first
        if not self.check_auth():
            return

        upload_id = self.request.headers.get("X-Upload-Id", "")
        rel_path_encoded = self.request.headers.get("X-Rel-Path", "")

        if not upload_id or not rel_path_encoded:
            self.set_status(400)
            self.finish({"status": "error", "detail": "missing X-Upload-Id or X-Rel-Path header"})
            return

        # Validate upload_id: must be a safe alphanumeric token
        if not _SAFE_UPLOAD_ID.fullmatch(upload_id):
            self.set_status(400)
            self.finish({"status": "error", "detail": "invalid upload_id format"})
            return

        rel_path = urllib.parse.unquote(rel_path_encoded)
        safe_rel = _safe_rel_path(rel_path)
        if safe_rel is None:
            self.set_status(400)
            self.finish({"status": "error", "detail": "invalid rel_path"})
            return

        # Extension allowlist for uploaded files
        ext = safe_rel.suffix.lower()
        if ext and ext not in _ALLOWED_UPLOAD_EXTENSIONS:
            self.set_status(400)
            self.finish({"status": "error", "detail": f"file type '{ext}' is not permitted"})
            return

        staging_dir = _UPLOAD_ROOT / upload_id  # upload_id is now validated safe
        self.dest_path = (staging_dir / safe_rel).resolve()
        staging_res = staging_dir.resolve()

        if staging_res != self.dest_path and staging_res not in self.dest_path.parents:
            self.set_status(400)
            self.finish({"status": "error", "detail": "path traversal detected"})
            return

        self.dest_path.parent.mkdir(parents=True, exist_ok=True)
        self._bytes_written: int = 0
        self.file_handle = open(self.dest_path, "wb")

    def data_received(self, chunk: bytes) -> None:
        if hasattr(self, "file_handle") and not self.file_handle.closed:
            self._bytes_written = getattr(self, "_bytes_written", 0) + len(chunk)
            if self._bytes_written > _MAX_UPLOAD_BYTES:
                self.file_handle.close()
                try:
                    self.dest_path.unlink(missing_ok=True)
                except Exception:
                    pass
                self.set_status(413)
                self.finish({"status": "error", "detail": "upload exceeds 5 GB limit"})
                return
            self.file_handle.write(chunk)

    def post(self) -> None:
        if hasattr(self, "file_handle") and not self.file_handle.closed:
            self.file_handle.close()
        self.write({"status": "ok"})


class UploadFinishHandler(SecureMixin, tornado.web.RequestHandler):

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    async def post(self) -> None:
        if not self.check_auth():
            return
        try:
            body = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            self.write({"status": "error", "detail": "invalid JSON"})
            return

        upload_id = body.get("upload_id", "")
        mode = body.get("mode", "figure")

        if not upload_id:
            self.set_status(400)
            self.write({"status": "error", "detail": "missing upload_id"})
            return

        # Validate upload_id before using it in a path
        if not _SAFE_UPLOAD_ID.fullmatch(str(upload_id)):
            self.set_status(400)
            self.write({"status": "error", "detail": "invalid upload_id format"})
            return

        staging_dir = _UPLOAD_ROOT / str(upload_id)
        if not staging_dir.exists():
            self.set_status(404)
            self.write({"status": "error", "detail": "upload not found"})
            return

        try:
            if mode == "figure":
                foam_files = sorted(staging_dir.rglob("*.foam"))
                if not foam_files:
                    self.set_status(400)
                    self.write({"status": "error", "detail": _OPENFOAM_ONLY_FIGURE_ERROR})
                    return

                foam_path = foam_files[0]

                log_lines: list[str] = []
                dest_foam = create_case_symlink(
                    foam_path=foam_path,
                    dest_data_dir=_PROJECT_ROOT / "data",
                    log_lines=log_lines,
                )

                src = dest_foam.relative_to(_PROJECT_ROOT).as_posix()
                fig_id = _slugify_fig_id(foam_path.parent.name)

                try:
                    await asyncio.wait_for(
                        _render_lock.acquire(), timeout=_LOCK_ACQUIRE_TIMEOUT_S
                    )
                except asyncio.TimeoutError:
                    self.set_status(503)
                    self.write({
                        "status": "error",
                        "detail": "A compile is currently running — try again shortly.",
                        "log": log_lines[-20:],
                    })
                    return
                try:
                    loop = asyncio.get_running_loop()
                    proc = await loop.run_in_executor(
                        None, _run_preview_subprocess, dest_foam, fig_id, "auto"
                    )
                except subprocess.TimeoutExpired:
                    self.set_status(500)
                    self.write({
                        "status": "error",
                        "detail": "Figure preview render timed out.",
                        "log": log_lines[-20:],
                    })
                    return
                finally:
                    _render_lock.release()

                if proc.returncode != 0:
                    detail = (proc.stderr or "").strip()[-2000:] or "preview render failed"
                    self.set_status(500)
                    self.write({
                        "status": "error",
                        "detail": f"Figure preview render failed: {detail}",
                        "log": log_lines[-20:],
                    })
                    return

                result = _parse_preview_stdout(proc.stdout)
                if result is None or result.get("status") != "ok":
                    self.set_status(500)
                    self.write({
                        "status": "error",
                        "detail": "Figure preview render returned an invalid status.",
                        "log": log_lines[-20:],
                    })
                    return

                field = result.get("field") or ""
                fields = [f for f in (result.get("fields") or []) if isinstance(f, str)]
                log_lines.append(f"  Rendered preview figure '{fig_id}' (field: {field or 'none'})")

                shortcode = generate_shortcode(
                    src=src,
                    field=field,
                    fig_id=fig_id,
                    time="mid",
                    caption="",
                    fields=fields,
                )

                self.write(
                    {
                        "status": "ok",
                        "shortcode": shortcode,
                        "src": src,
                        "fig_id": fig_id,
                        "log": log_lines[-20:],
                    }
                )

            else:
                all_files = sorted(staging_dir.rglob("*"))
                file_list = [f for f in all_files if f.is_file()]

                if not file_list:
                    self.set_status(400)
                    self.write({"status": "error", "detail": "No files found"})
                    return

                lower_suffixes = {f.suffix.lower() for f in file_list}
                if ".h5" in lower_suffixes and not ({".xdmf", ".xmf"} & lower_suffixes):
                    self.set_status(400)
                    self.write({"status": "error", "detail": _RAW_H5_UPLOAD_ERROR})
                    return

                copied_paths = []
                for src_file in file_list:
                    rel_name = src_file.name
                    dest_file = _PROJECT_ROOT / "data" / rel_name

                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    if dest_file.exists():
                        dest_file.unlink()

                    # Copy, never symlink: src_file lives under the staging dir
                    # that the finally block deletes, so a symlink would dangle.
                    shutil.copy2(src_file, dest_file)

                    copied_paths.append(str(dest_file.relative_to(_PROJECT_ROOT)))

                first_file = copied_paths[0]
                shortcode = f"{{{{< include {first_file} >}}}}"

                self.write({
                    "status": "ok",
                    "shortcode": shortcode,
                    "files": copied_paths,
                })

        finally:
            try:
                shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception:
                pass


ROUTES = [
    (r"/upload/file", UploadFileHandler),
    (r"/upload/finish", UploadFinishHandler),
]
