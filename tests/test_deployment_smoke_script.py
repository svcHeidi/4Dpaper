"""Regression checks for the Docker deployment smoke test script."""
from __future__ import annotations

from pathlib import Path


def test_deployment_smoke_script_covers_expected_checks():
    text = (Path(__file__).parent / "e2e" / "smoke_deployment.sh").read_text(encoding="utf-8")

    assert "/api/health" in text
    assert "/api/files" in text
    assert "/api/compile" in text
    assert "/api/export" in text
    assert "/output/main.html" in text
    assert "/state/upload_tmp/probe/secret.txt" in text
    assert "FOURD_DROP_PRIVILEGES=1" in text
    assert "FOURD_CHOWN_WORKSPACE=1" in text
