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
    assert "/quick.html" in text
    assert "/api/quick-target" in text
    assert "FOURD_DROP_PRIVILEGES=1" in text
    assert "FOURD_CHOWN_WORKSPACE=1" in text
    assert 'APP_VERSION=$(cat VERSION)' in text


def test_quick_smoke_script_covers_isolation_and_retained_html():
    text = (Path(__file__).parent / "e2e" / "smoke_quick_export.sh").read_text(
        encoding="utf-8"
    )

    assert "/api/quick-init" in text
    assert "/api/quick-export" in text
    assert "/workspace/source false" in text
    assert "/quick-output true" in text
    assert "SOURCE_HASH_BEFORE" in text
    assert "fig-test_data.html" in text
    assert "fig-test_data-standalone.html" in text
    assert "test ! -e \"$RUNTIME_WORKSPACE\"" in text
