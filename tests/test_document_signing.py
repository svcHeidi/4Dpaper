"""Tests for dashboard/document_signing.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def _write_keypair(tmp_path: Path) -> tuple[Path, Path]:
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
    return private_path, public_path


def test_sign_and_verify_round_trip(tmp_path):
    from dashboard.document_signing import sign_html, verify_signed_html

    private_path, public_path = _write_keypair(tmp_path)
    signed = sign_html("<html><body>hello</body></html>", private_path, key_id="docker-main")
    result = verify_signed_html(signed, public_key_path=public_path)

    assert result.is_valid is True
    assert result.is_signed is True
    assert result.metadata is not None
    assert result.metadata["kid"] == "docker-main"
    assert result.reason == "signature valid"


def test_verify_detects_tampering(tmp_path):
    from dashboard.document_signing import sign_html, verify_signed_html

    private_path, public_path = _write_keypair(tmp_path)
    signed = sign_html("<html><body>hello</body></html>", private_path)
    tampered = signed.replace("hello", "hullo", 1)
    result = verify_signed_html(tampered, public_key_path=public_path)

    assert result.is_valid is False
    assert result.is_signed is True


def test_duplicate_markers_are_rejected(tmp_path):
    from dashboard.document_signing import sign_html, verify_signed_html

    private_path, public_path = _write_keypair(tmp_path)
    signed = sign_html("<html><body>hello</body></html>", private_path)
    duplicated = f"{signed}\n{signed.splitlines()[-1]}"
    result = verify_signed_html(duplicated, public_key_path=public_path)

    assert result.is_valid is False
    assert result.reason == "duplicate signature markers found"
