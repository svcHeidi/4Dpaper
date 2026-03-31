"""
Panel upload plugin: stage dropped OpenFOAM case folders into `data/`
and generate a default 4d-image shortcode.

This is intentionally narrow: it only targets default insertion and
reuses existing core logic (`copy_case_data`, `generate_shortcode`).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import tornado.web

_PROJECT_ROOT = Path(__file__).parent.parent
_UPLOAD_ROOT = _PROJECT_ROOT / "state" / "upload_tmp"


def generate_shortcode(
    *,
    src: str,
    field: str,
    fig_id: str,
    time: str,
    caption: str,
) -> str:
    """Return a ``{{< 4d-image ... >}}`` shortcode string."""
    parts = [f'src="{src}"', f'field="{field}"', f'id="{fig_id}"']
    if time and time != "mid":
        parts.append(f'time="{time}"')
    if caption.strip():
        parts.append(f'caption="{caption.strip()}"')
    return "{{< 4d-image " + " ".join(parts) + " >}}"


def copy_case_data(foam_path: Path, dest_data_dir: Path, log_lines: list[str]) -> Path:
    """
    Copy the minimal OpenFOAM case files required for PyVista rendering into
    *dest_data_dir*/<case_name>/.

    Copies:
    - The .foam marker file
    - constant/polyMesh/
    - processor*/constant/polyMesh/
    - processor*/<timestep>/ (all timesteps)

    Returns the path to the new .foam marker file.
    """
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
    """
    Convert a browser-provided relative path into a safe Path that cannot escape.
    Rejects absolute paths and any '..' segments.
    """
    try:
        p = Path(rel_path)
    except Exception:
        return None

    # Reject absolute paths
    if p.is_absolute():
        return None

    parts = list(p.parts)
    if any(part in ("..", "") for part in parts):
        return None

    # Reject windows drive-like first part (e.g. "C:")
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

        # Final escape check
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
            foam_files = sorted(staging_dir.rglob("*.foam"))
            if not foam_files:
                self.set_status(400)
                self.write({"status": "error", "detail": "No .foam file found in dropped folder"})
                return

            foam_path = foam_files[0]

            # Reuse existing copy + shortcode logic so we don't fork behavior.
            log_lines: list[str] = []
            dest_foam = copy_case_data(
                foam_path=foam_path,
                dest_data_dir=_PROJECT_ROOT / "data",
                log_lines=log_lines,
            )

            src = dest_foam.relative_to(_PROJECT_ROOT).as_posix()

            # Default insertion (as requested): keep parity with the form defaults.
            shortcode = generate_shortcode(
                src=src,
                field="Vm",
                fig_id="fig-vm",
                time="mid",
                caption="",
            )

            # Cleanup staging to keep disk usage bounded.
            try:
                shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception:
                pass

            self.write(
                {
                    "status": "ok",
                    "shortcode": shortcode,
                    "src": src,
                    "fig_id": "fig-vm",
                    "log": log_lines[-20:],
                }
            )
        finally:
            # Cleanup in case of exceptions as well.
            try:
                shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception:
                pass


ROUTES = [
    (r"/upload/file", UploadFileHandler),
    (r"/upload/finish", UploadFinishHandler),
]

