"""Stage uploaded files and return default shortcodes."""
from __future__ import annotations

import json
import os
import re
import shutil
import urllib.parse
from pathlib import Path

import tornado.web

from dashboard.auth import SecureMixin

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))
_UPLOAD_ROOT = _PROJECT_ROOT / "state" / "upload_tmp"

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


def generate_shortcode(
    *,
    src: str,
    field: str,
    fig_id: str,
    time: str,
    caption: str,
) -> str:
    """Build a default `4d-image` shortcode."""
    parts = [f'src="{src}"', f'field="{field}"', f'id="{fig_id}"']
    if time and time != "mid":
        parts.append(f'time="{time}"')
    if caption.strip():
        parts.append(f'caption="{caption.strip()}"')
    return "{{< 4d-image " + " ".join(parts) + " >}}"


def create_case_symlink(
    foam_path: Path,
    dest_data_dir: Path,
    log_lines: list[str]
) -> Path:
    """Symlink a case directory into `data/` and fall back to copy on failure."""
    case_root = foam_path.parent
    case_name = case_root.name
    dest_case = dest_data_dir / case_name

    if dest_case.exists() or dest_case.is_symlink():
        if dest_case.is_symlink():
            dest_case.unlink()
        else:
            shutil.rmtree(dest_case)

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

    def post(self) -> None:
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
                    self.write({"status": "error", "detail": "No .foam file found in dropped folder"})
                    return

                foam_path = foam_files[0]

                log_lines: list[str] = []
                dest_foam = create_case_symlink(
                    foam_path=foam_path,
                    dest_data_dir=_PROJECT_ROOT / "data",
                    log_lines=log_lines,
                )

                src = dest_foam.relative_to(_PROJECT_ROOT).as_posix()

                shortcode = generate_shortcode(
                    src=src,
                    field="Vm",
                    fig_id="fig-vm",
                    time="mid",
                    caption="",
                )

                self.write(
                    {
                        "status": "ok",
                        "shortcode": shortcode,
                        "src": src,
                        "fig_id": "fig-vm",
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

                copied_paths = []
                for src_file in file_list:
                    rel_name = src_file.name
                    dest_file = _PROJECT_ROOT / "data" / rel_name

                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    if dest_file.exists():
                        dest_file.unlink()

                    try:
                        dest_file.symlink_to(src_file.resolve())
                    except (OSError, NotImplementedError):
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
