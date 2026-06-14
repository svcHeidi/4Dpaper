"""Cryptographic signing helpers for 4Dpapers HTML documents."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

SIGNATURE_MARKER = "4DPAPERS_SIGNATURE_V1"
_COMMENT_RE = re.compile(
    rf"<!--\s*{SIGNATURE_MARKER}\s+(?P<payload>\{{.*?\}})\s*-->",
    re.DOTALL,
)
_TAIL_RE = re.compile(
    rf"(?s)^(?P<unsigned>.*)<!--\s*{SIGNATURE_MARKER}\s+(?P<payload>\{{.*?\}})\s*-->\s*$"
)

ENV_PRIVATE_KEY_PATH = "FOURD_SIGNING_PRIVATE_KEY_PATH"
ENV_PUBLIC_KEY_PATH = "FOURD_SIGNING_PUBLIC_KEY_PATH"
ENV_KEY_ID = "FOURD_SIGNING_KEY_ID"


@dataclass(slots=True)
class VerificationResult:
    """Structured result for signed HTML verification."""

    is_valid: bool
    is_signed: bool
    reason: str
    metadata: dict | None = None
    unsigned_sha256: str | None = None

    def to_dict(self) -> dict:
        return {
            "valid": self.is_valid,
            "signed": self.is_signed,
            "reason": self.reason,
            "metadata": self.metadata,
            "unsigned_sha256": self.unsigned_sha256,
        }


def get_private_key_path() -> Path | None:
    raw = os.getenv(ENV_PRIVATE_KEY_PATH, "").strip()
    return Path(raw) if raw else None


def get_public_key_path() -> Path | None:
    raw = os.getenv(ENV_PUBLIC_KEY_PATH, "").strip()
    return Path(raw) if raw else None


def _load_private_key(path: Path) -> ed25519.Ed25519PrivateKey:
    data = path.read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise TypeError(f"{path} does not contain an Ed25519 private key")
    return key


def _load_public_key(path: Path) -> ed25519.Ed25519PublicKey:
    data = path.read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, ed25519.Ed25519PublicKey):
        raise TypeError(f"{path} does not contain an Ed25519 public key")
    return key


def _resolve_public_key(public_key_path: Path | None = None) -> ed25519.Ed25519PublicKey:
    if public_key_path is not None:
        return _load_public_key(public_key_path)

    configured_public = get_public_key_path()
    if configured_public is not None:
        return _load_public_key(configured_public)

    configured_private = get_private_key_path()
    if configured_private is not None:
        return _load_private_key(configured_private).public_key()

    raise FileNotFoundError(
        f"No verification key configured. Set {ENV_PUBLIC_KEY_PATH} or {ENV_PRIVATE_KEY_PATH}."
    )


def _public_key_sha256(public_key: ed25519.Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def _unsigned_sha256(unsigned_html: str) -> str:
    return hashlib.sha256(unsigned_html.encode("utf-8")).hexdigest()


def strip_signature_block(html: str) -> str:
    """Remove a trailing 4Dpapers signature block when present."""
    matches = list(_COMMENT_RE.finditer(html))
    if not matches:
        return html
    if len(matches) > 1:
        raise ValueError("duplicate signature markers found")
    tail = _TAIL_RE.fullmatch(html)
    if tail is None:
        raise ValueError("signature marker must appear exactly once at end of document")
    return tail.group("unsigned")


def sign_html(unsigned_html: str, private_key_path: Path, key_id: str | None = None) -> str:
    """Append a signature marker comment to an HTML document."""
    cleaned = strip_signature_block(unsigned_html)
    private_key = _load_private_key(private_key_path)
    public_key = private_key.public_key()
    separator = "" if cleaned.endswith(("\n", "\r")) else "\n"
    signed_region = f"{cleaned}{separator}"
    signature = private_key.sign(signed_region.encode("utf-8"))
    payload = {
        "version": 1,
        "alg": "Ed25519",
        "kid": key_id or os.getenv(ENV_KEY_ID, "default"),
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "public_key_sha256": _public_key_sha256(public_key),
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    comment = f"<!-- {SIGNATURE_MARKER} {json.dumps(payload, separators=(',', ':'))} -->"
    return f"{signed_region}{comment}"


def sign_html_file(file_path: Path, private_key_path: Path, key_id: str | None = None) -> None:
    signed = sign_html(file_path.read_text(encoding="utf-8"), private_key_path, key_id=key_id)
    file_path.write_text(signed, encoding="utf-8")


def sign_html_file_if_configured(file_path: Path, key_id: str | None = None) -> bool:
    """Sign an HTML file when FOURD_SIGNING_PRIVATE_KEY_PATH is configured."""
    private_key_path = get_private_key_path()
    if private_key_path is None:
        return False
    sign_html_file(file_path, private_key_path, key_id=key_id)
    return True


def verify_signed_html(
    full_html: str,
    public_key_path: Path | None = None,
    *,
    require_signature: bool = True,
) -> VerificationResult:
    """Verify the trailing signature marker on a signed HTML document."""
    try:
        matches = list(_COMMENT_RE.finditer(full_html))
        if not matches:
            if require_signature:
                return VerificationResult(False, False, "signature missing")
            return VerificationResult(True, False, "unsigned document")
        if len(matches) > 1:
            return VerificationResult(False, True, "duplicate signature markers found")

        tail = _TAIL_RE.fullmatch(full_html)
        if tail is None:
            return VerificationResult(False, True, "signature marker must appear at end of document")

        unsigned = tail.group("unsigned")
        payload = json.loads(tail.group("payload"))
        signature_b64 = payload.get("signature")
        if not isinstance(signature_b64, str) or not signature_b64:
            return VerificationResult(False, True, "signature payload missing signature")
        if payload.get("alg") != "Ed25519":
            return VerificationResult(False, True, "unsupported signature algorithm")

        signature = base64.b64decode(signature_b64, validate=True)
        public_key = _resolve_public_key(public_key_path)
        expected_fp = payload.get("public_key_sha256")
        actual_fp = _public_key_sha256(public_key)
        if expected_fp and expected_fp != actual_fp:
            return VerificationResult(False, True, "signature key fingerprint mismatch", metadata=payload)

        public_key.verify(signature, unsigned.encode("utf-8"))
        return VerificationResult(
            True,
            True,
            "signature valid",
            metadata=payload,
            unsigned_sha256=_unsigned_sha256(unsigned),
        )
    except FileNotFoundError as exc:
        return VerificationResult(False, True, str(exc))
    except json.JSONDecodeError:
        return VerificationResult(False, True, "signature payload is not valid JSON")
    except ValueError as exc:
        return VerificationResult(False, True, str(exc))
    except Exception:
        return VerificationResult(False, True, "signature verification failed")


def verify_signed_html_file(
    file_path: Path,
    public_key_path: Path | None = None,
    *,
    require_signature: bool = True,
) -> VerificationResult:
    return verify_signed_html(
        file_path.read_text(encoding="utf-8"),
        public_key_path=public_key_path,
        require_signature=require_signature,
    )
