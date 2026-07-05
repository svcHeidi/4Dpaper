"""Regression tests for upload staging and finish behavior."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import tornado.web
from tornado.testing import AsyncHTTPTestCase

import dashboard.auth as auth
import dashboard.upload_plugin as upload_plugin


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

    def test_figure_mode_copies_staged_openfoam_case_into_data_dir(self):
        staged = self._upload_file("upload_foam_case", "demo/case.foam")
        assert staged.code == 200

        response = self._finish("upload_foam_case")
        assert response.code == 200

        payload = json.loads(response.body)
        assert payload["status"] == "ok"
        assert payload["src"] == "data/demo/case.foam"
        assert payload["shortcode"].startswith("{{< 4d-image ")
        assert (self.root / "data" / "demo" / "case.foam").exists()
        assert not (self.root / "state" / "upload_tmp" / "upload_foam_case").exists()

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
