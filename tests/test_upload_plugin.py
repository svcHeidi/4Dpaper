"""Regression tests for upload staging and finish behavior."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import tornado.web
from tornado.testing import AsyncHTTPTestCase

import dashboard.auth as auth
import dashboard.upload_plugin as upload_plugin

_PREVIEW_OK_STDOUT = (
    "Generated (PNG): state/figures/fig-demo.png\n"
    '{"status": "ok", "field": "Vm", "fields": ["Vm", "p"]}\n'
)


class UploadPluginTest(AsyncHTTPTestCase):
    def get_app(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_api_key = auth._API_KEY
        self.old_project_root = upload_plugin._PROJECT_ROOT
        self.old_upload_root = upload_plugin._UPLOAD_ROOT

        auth._API_KEY = "test-key"
        upload_plugin._PROJECT_ROOT = self.root
        upload_plugin._UPLOAD_ROOT = self.root / "state" / "upload_tmp"

        return tornado.web.Application(upload_plugin.ROUTES)

    def tearDown(self):
        auth._API_KEY = self.old_api_key
        upload_plugin._PROJECT_ROOT = self.old_project_root
        upload_plugin._UPLOAD_ROOT = self.old_upload_root
        self.tmp.cleanup()
        super().tearDown()

    def _upload_file(self, upload_id: str, rel_path: str, body: bytes = b"fixture"):
        return self.fetch(
            "/upload/file",
            method="POST",
            headers={
                "X-API-Key": "test-key",
                "X-Upload-Id": upload_id,
                "X-Rel-Path": rel_path,
            },
            body=body,
            raise_error=False,
        )

    def _finish(self, upload_id: str, *, mode: str = "figure"):
        return self.fetch(
            "/upload/finish",
            method="POST",
            headers={
                "X-API-Key": "test-key",
                "Content-Type": "application/json",
            },
            body=json.dumps({"upload_id": upload_id, "mode": mode}),
            raise_error=False,
        )

    def test_figure_mode_requires_openfoam_case_folder(self):
        staged = self._upload_file("upload_vtu_case", "ref_block.vtu")
        assert staged.code == 200

        response = self._finish("upload_vtu_case")
        assert response.code == 400
        payload = json.loads(response.body)
        assert payload["detail"] == (
            "Figure upload currently supports OpenFOAM case folders only. "
            "No .foam file was found in the dropped folder."
        )

    def _stub_preview(self, returncode: int = 0, stdout: str = _PREVIEW_OK_STDOUT,
                      stderr: str = "") -> None:
        """Replace the preview render subprocess with a canned result."""
        result = subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr
        )
        had = hasattr(upload_plugin, "_run_preview_subprocess")
        old = getattr(upload_plugin, "_run_preview_subprocess", None)
        upload_plugin._run_preview_subprocess = lambda *a, **k: result

        def _restore():
            if had:
                upload_plugin._run_preview_subprocess = old
            else:
                delattr(upload_plugin, "_run_preview_subprocess")

        self.addCleanup(_restore)

    def test_figure_mode_copies_staged_openfoam_case_into_data_dir(self):
        self._stub_preview()
        staged = self._upload_file("upload_foam_case", "demo/case.foam")
        assert staged.code == 200

        response = self._finish("upload_foam_case")
        assert response.code == 200

        payload = json.loads(response.body)
        assert payload["status"] == "ok"
        assert payload["src"] == "data/demo/case.foam"
        assert payload["fig_id"] == "fig-demo"
        assert payload["shortcode"].startswith("{{< 4d-image ")
        assert 'field="Vm"' in payload["shortcode"]
        assert 'fields="Vm,p"' in payload["shortcode"]
        assert (self.root / "data" / "demo" / "case.foam").exists()
        assert not (self.root / "state" / "upload_tmp" / "upload_foam_case").exists()

    def test_figure_mode_fails_when_preview_render_fails(self):
        self._stub_preview(returncode=1, stdout="", stderr="RuntimeError: no time steps")
        staged = self._upload_file("upload_bad_case", "bad/case.foam")
        assert staged.code == 200

        response = self._finish("upload_bad_case")
        assert response.code == 500

        payload = json.loads(response.body)
        assert payload["status"] == "error"
        assert "shortcode" not in payload
        assert "no time steps" in payload["detail"]

    def test_figure_mode_returns_503_when_render_lock_busy(self):
        self._stub_preview()
        old_timeout = upload_plugin._LOCK_ACQUIRE_TIMEOUT_S
        upload_plugin._LOCK_ACQUIRE_TIMEOUT_S = 0.05
        self.addCleanup(
            lambda: setattr(upload_plugin, "_LOCK_ACQUIRE_TIMEOUT_S", old_timeout)
        )
        staged = self._upload_file("upload_busy_case", "busy/case.foam")
        assert staged.code == 200

        self.io_loop.run_sync(upload_plugin._render_lock.acquire)
        try:
            response = self._finish("upload_busy_case")
        finally:
            upload_plugin._render_lock.release()

        assert response.code == 503
        payload = json.loads(response.body)
        assert payload["status"] == "error"
        assert "shortcode" not in payload

    def test_file_mode_rejects_standalone_h5_upload(self):
        staged = self._upload_file("upload_h5_only", "test_data.h5")
        assert staged.code == 200

        response = self._finish("upload_h5_only", mode="file")
        assert response.code == 400

        payload = json.loads(response.body)
        assert payload["detail"] == (
            "Generic .h5 uploads are not supported. Use .hdf5 for generic HDF5 data, "
            "or upload .h5 only as a companion file alongside an .xdmf or .xmf dataset."
        )

    def test_file_mode_allows_xdmf_with_h5_companion(self):
        staged_h5 = self._upload_file("upload_xdmf_pair", "fiber_directions.h5")
        staged_xdmf = self._upload_file("upload_xdmf_pair", "fiber_directions.xdmf")
        assert staged_h5.code == 200
        assert staged_xdmf.code == 200

        response = self._finish("upload_xdmf_pair", mode="file")
        assert response.code == 200

        payload = json.loads(response.body)
        assert payload["status"] == "ok"
        assert set(payload["files"]) == {
            "data/fiber_directions.h5",
            "data/fiber_directions.xdmf",
        }


class UploadFileModeStagingTest(AsyncHTTPTestCase):
    """File-mode staged uploads must leave real files, not dangling symlinks."""

    def get_app(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_api_key = auth._API_KEY
        self.old_project_root = upload_plugin._PROJECT_ROOT
        self.old_upload_root = upload_plugin._UPLOAD_ROOT
        auth._API_KEY = "test-key"
        upload_plugin._PROJECT_ROOT = self.root
        upload_plugin._UPLOAD_ROOT = self.root / "state" / "upload_tmp"
        return tornado.web.Application(upload_plugin.ROUTES)

    def tearDown(self):
        auth._API_KEY = self.old_api_key
        upload_plugin._PROJECT_ROOT = self.old_project_root
        upload_plugin._UPLOAD_ROOT = self.old_upload_root
        self.tmp.cleanup()
        super().tearDown()

    def test_file_mode_leaves_real_readable_file_after_staging_cleanup(self):
        self.fetch(
            "/upload/file",
            method="POST",
            headers={
                "X-API-Key": "test-key",
                "X-Upload-Id": "upload_csv_file",
                "X-Rel-Path": "table.csv",
            },
            body=b"a,b\n1,2\n",
            raise_error=False,
        )
        response = self.fetch(
            "/upload/finish",
            method="POST",
            headers={"X-API-Key": "test-key", "Content-Type": "application/json"},
            body=json.dumps({"upload_id": "upload_csv_file", "mode": "file"}),
            raise_error=False,
        )
        assert response.code == 200

        staged = self.root / "data" / "table.csv"
        # Staging dir is deleted in the finally block; a symlink into it would
        # now dangle.
        assert not (self.root / "state" / "upload_tmp" / "upload_csv_file").exists()
        assert staged.exists(), "staged file is missing or a dangling symlink"
        assert staged.read_bytes() == b"a,b\n1,2\n"


def test_copy_case_data_copies_serial_time_dirs_and_system(tmp_path):
    case = tmp_path / "src" / "demo"
    (case / "system").mkdir(parents=True)
    (case / "system" / "controlDict").write_text("FoamFile {}")
    (case / "constant" / "polyMesh").mkdir(parents=True)
    (case / "constant" / "polyMesh" / "points").write_text("()")
    for t in ("0", "0.1"):
        (case / t).mkdir()
        (case / t / "T").write_text("dimensions [0 0 0 1 0 0 0];")
    (case / "notes").mkdir()  # non-numeric dir must not be copied
    foam = case / "case.foam"
    foam.write_text("")

    dest = tmp_path / "data"
    dest.mkdir()
    out = upload_plugin.copy_case_data(foam, dest, [])

    root = dest / "demo"
    assert out == root / "case.foam"
    assert (root / "system" / "controlDict").exists()
    assert (root / "constant" / "polyMesh" / "points").exists()
    assert (root / "0" / "T").exists()
    assert (root / "0.1" / "T").exists()
    assert not (root / "notes").exists()


def test_slugify_fig_id_normalizes_case_name():
    assert upload_plugin._slugify_fig_id("Demo Case 01") == "fig-demo-case-01"
    assert upload_plugin._slugify_fig_id("aorta_v2") == "fig-aorta_v2"


def test_slugify_fig_id_falls_back_when_slug_empty():
    assert upload_plugin._slugify_fig_id("") == "fig-case"
    assert upload_plugin._slugify_fig_id("***") == "fig-case"


def test_generate_shortcode_emits_fields_attribute_for_multiple_fields():
    shortcode = upload_plugin.generate_shortcode(
        src="data/x/case.foam", field="U", fig_id="fig-x",
        time="mid", caption="", fields=["U", "p"],
    )
    assert 'fields="U,p"' in shortcode


def test_generate_shortcode_omits_fields_attribute_for_single_field():
    shortcode = upload_plugin.generate_shortcode(
        src="data/x/case.foam", field="U", fig_id="fig-x",
        time="mid", caption="", fields=["U"],
    )
    assert "fields=" not in shortcode
