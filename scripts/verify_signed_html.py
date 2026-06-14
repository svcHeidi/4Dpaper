#!/usr/bin/env python3
"""Verify a signed 4Dpapers HTML document locally."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.document_signing import verify_signed_html_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a signed 4Dpapers HTML file")
    parser.add_argument("html_file", type=Path, help="HTML document to verify")
    parser.add_argument(
        "--public-key",
        type=Path,
        default=None,
        help="Public PEM file to verify against (defaults to FOURD_SIGNING_PUBLIC_KEY_PATH)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    args = parser.parse_args()

    result = verify_signed_html_file(args.html_file, public_key_path=args.public_key)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"valid: {result.is_valid}")
        print(f"signed: {result.is_signed}")
        print(f"reason: {result.reason}")
        if result.metadata:
            print(f"kid: {result.metadata.get('kid')}")
            print(f"created_at: {result.metadata.get('created_at')}")
        if result.unsigned_sha256:
            print(f"unsigned_sha256: {result.unsigned_sha256}")
    return 0 if result.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
