"""Stage uploaded files and return default shortcodes."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import tornado.web

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))
_UPLOAD_ROOT = _PROJECT_ROOT / "state" / "upload_tmp"


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
        log_lines.append(f"  Symlinked {case_root} → {dest_case}")
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


class UploadFileHandler(tornado.web.RequestHandler):
    def post(self) -> None:
        upload_id = self.get_body_argument("upload_id", default=None)
        rel_path = self.get_body_argument("rel_path", default=None)

        if not upload_id or not rel_path:
            self.set_status(400)
            self.write({"status": "error", "detail": "missing upload_id or rel_path"})
            return

        safe_rel = _safe_rel_path(rel_path)
        if safe_rel is None:
            self.set_status(400)
            self.write({"status": "error", "detail": "invalid rel_path"})
            return

        if not self.request.files or "file" not in self.request.files:
            self.set_status(400)
            self.write({"status": "error", "detail": "missing multipart file"})
            return

        file_list = self.request.files["file"]
        if not file_list:
            self.set_status(400)
            self.write({"status": "error", "detail": "empty file upload"})
            return

        file_info = file_list[0]
        body = file_info.get("body")
        if body is None:
            self.set_status(400)
            self.write({"status": "error", "detail": "empty file body"})
            return

        staging_dir = _UPLOAD_ROOT / str(upload_id)
        dest_path = (staging_dir / safe_rel).resolve()
        staging_res = staging_dir.resolve()

        if staging_res != dest_path and staging_res not in dest_path.parents:
            self.set_status(400)
            self.write({"status": "error", "detail": "path traversal detected"})
            return

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(body)
        self.write({"status": "ok"})


class UploadFinishHandler(tornado.web.RequestHandler):
    def post(self) -> None:
        try:
            body = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            self.write({"status": "error", "detail": "invalid JSON"})
            return

        upload_id = body.get("upload_id")
        mode = body.get("mode", "figure")

        if not upload_id:
            self.set_status(400)
            self.write({"status": "error", "detail": "missing upload_id"})
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
