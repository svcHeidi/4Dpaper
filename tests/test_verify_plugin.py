"""Tests for the signed-document verify endpoint."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("tornado")


def _make_verify_handler(body_bytes: bytes = b"", *, files: dict | None = None):
    from dashboard.verify_plugin import VerifyDocumentHandler

    request = MagicMock()
    request.body = body_bytes
    request.files = files or {}
    request.headers = {}
    handler = VerifyDocumentHandler.__new__(VerifyDocumentHandler)
    handler.request = request
    handler.write = MagicMock()
    handler.set_status = MagicMock()
    handler.finish = MagicMock()
    handler.set_header = MagicMock()
    return handler


def test_verify_handler_in_routes():
    from dashboard.verify_plugin import VerifyDocumentHandler, ROUTES

    assert VerifyDocumentHandler is not None
    assert any("/api/verify" in route for route, _ in ROUTES)


def test_verify_handler_returns_result_for_json_body(tmp_path):
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from dashboard.document_signing import sign_html

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    signed = sign_html("<html><body>ok</body></html>", private_path)
    body = json.dumps({"filename": "paper.html", "html": signed}).encode()
    handler = _make_verify_handler(body)

    from unittest.mock import patch

    with patch("dashboard.verify_plugin.verify_signed_html") as mock_verify:
        from dashboard.document_signing import verify_signed_html

        mock_verify.side_effect = lambda html: verify_signed_html(html, public_key_path=public_path)
        handler.post()

    payload = handler.write.call_args[0][0]
    assert payload["filename"] == "paper.html"
    assert payload["valid"] is True
    assert payload["signed"] is True


def test_verify_handler_rejects_missing_html():
    handler = _make_verify_handler(b"{}")
    handler.post()
    handler.set_status.assert_called_once_with(400)
