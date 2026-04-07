"""
Panel upload plugin: stage dropped OpenFOAM case folders into `data/`
and generate a default 4d-image shortcode.

This is intentionally narrow: it only targets default insertion and
reuses existing core logic (`copy_case_data`, `generate_shortcode`).
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import tornado.web

# PROJECT_ROOT can be set via environment variable (for Docker) or defaults to parent directory
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
    """Return a ``{{< 4d-image ... >}}`` shortcode string."""
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
    """
    Create a symlink to the OpenFOAM case folder (instead of copying).

    This allows data to be auto-updated when simulations re-run on HPC:
    if the source case is updated, the symlink automatically points to
    the new results without manual re-configuration.

    Returns the path to the symlink'd .foam marker file.

    Falls back to copy_case_data() if symlink creation fails (e.g., on Windows).
    """
    case_root = foam_path.parent
    case_name = case_root.name
    dest_case = dest_data_dir / case_name

    # Remove existing symlink/directory if present
    if dest_case.exists() or dest_case.is_symlink():
        if dest_case.is_symlink():
            dest_case.unlink()
        else:
            shutil.rmtree(dest_case)

    try:
        # Create symlink to the case folder
        dest_case.parent.mkdir(parents=True, exist_ok=True)
        dest_case.symlink_to(case_root)
        log_lines.append(f"  Symlinked {case_root} → {dest_case}")
        return dest_case / foam_path.name
    except (OSError, NotImplementedError) as e:
        # Fallback: if symlink fails (e.g., no permissions, Windows), copy instead
        log_lines.append(f"  Symlink failed ({e}), falling back to copy")
        return copy_case_data(foam_path, dest_data_dir, log_lines)


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

    Used as fallback if symlink creation fails, or when copying is explicitly desired.
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
        mode = body.get("mode", "figure")  # "figure" or "file"

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
                # Insert Figure: Find .foam file, symlink to data/
                foam_files = sorted(staging_dir.rglob("*.foam"))
                if not foam_files:
                    self.set_status(400)
                    self.write({"status": "error", "detail": "No .foam file found in dropped folder"})
                    return

                foam_path = foam_files[0]

                # Create symlink to the case (or copy if symlink fails)
                # This allows data to auto-update when HPC simulations are re-run
                log_lines: list[str] = []
                dest_foam = create_case_symlink(
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

                self.write(
                    {
                        "status": "ok",
                        "shortcode": shortcode,
                        "src": src,
                        "fig_id": "fig-vm",
                        "log": log_lines[-20:],
                    }
                )

            else:  # mode == "file"
                # Insert File: Copy arbitrary files to data/
                all_files = sorted(staging_dir.rglob("*"))
                file_list = [f for f in all_files if f.is_file()]

                if not file_list:
                    self.set_status(400)
                    self.write({"status": "error", "detail": "No files found"})
                    return

                # Symlink or copy files to data/
                copied_paths = []
                for src_file in file_list:
                    rel_name = src_file.name
                    dest_file = _PROJECT_ROOT / "data" / rel_name

                    # If file already exists with same name, use symlink approach
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    # Remove existing if present
                    if dest_file.exists():
                        dest_file.unlink()

                    # Create symlink (or copy if symlink fails)
                    try:
                        dest_file.symlink_to(src_file.resolve())
                    except (OSError, NotImplementedError):
                        # Fallback to copy if symlink fails
                        shutil.copy2(src_file, dest_file)

                    copied_paths.append(str(dest_file.relative_to(_PROJECT_ROOT)))

                # Generate include shortcode for first file
                # Example: {{< include data/references.bib >}}
                first_file = copied_paths[0]
                shortcode = f"{{{{< include {first_file} >}}}}"

                self.write({
                    "status": "ok",
                    "shortcode": shortcode,
                    "files": copied_paths,
                })

        finally:
            # Cleanup staging to keep disk usage bounded
            try:
                shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception:
                pass


ROUTES = [
    (r"/upload/file", UploadFileHandler),
    (r"/upload/finish", UploadFinishHandler),
]

