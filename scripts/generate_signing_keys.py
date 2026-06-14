#!/usr/bin/env python3
"""Generate an Ed25519 keypair for 4Dpapers HTML signing."""
from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def _write_file(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        path.chmod(mode)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 4Dpapers Ed25519 signing keys")
    parser.add_argument(
        "--private-key",
        type=Path,
        required=True,
        help="Path to write the private PEM file",
    )
    parser.add_argument(
        "--public-key",
        type=Path,
        required=True,
        help="Path to write the public PEM file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing key files",
    )
    args = parser.parse_args()

    for path in (args.private_key, args.public_key):
        if path.exists() and not args.force:
            parser.error(f"{path} already exists; use --force to overwrite")

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    _write_file(args.private_key, private_pem, 0o600)
    _write_file(args.public_key, public_pem, 0o644)

    print(f"Private key: {args.private_key}")
    print(f"Public key:  {args.public_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

