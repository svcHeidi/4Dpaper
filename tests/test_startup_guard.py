"""Tests for the fail-open startup security guard (``auth_startup_report``)."""

import importlib

import pytest


@pytest.fixture
def auth(monkeypatch):
    """Import a fresh copy of dashboard.auth with a clean environment.

    ``auth_startup_report`` reads the environment on each call, so a single
    import is sufficient — but we clear the relevant vars up front so leftover
    process env cannot influence the assertions.
    """
    monkeypatch.delenv("FOURD_API_KEY", raising=False)
    monkeypatch.delenv("FOURD_ALLOW_INSECURE", raising=False)
    import dashboard.auth as auth_mod

    return importlib.reload(auth_mod)


def test_ok_when_key_set(auth, monkeypatch):
    monkeypatch.setenv("FOURD_API_KEY", "s3cret")
    level, message = auth.auth_startup_report("0.0.0.0")
    assert level == "ok"
    assert message == ""


def test_refuse_when_no_key_on_all_interfaces(auth):
    level, message = auth.auth_startup_report("0.0.0.0")
    assert level == "refuse"
    assert "REFUSING TO START" in message


def test_refuse_when_no_key_on_empty_address(auth):
    # Empty address is the Bokeh default and binds all interfaces.
    level, _ = auth.auth_startup_report("")
    assert level == "refuse"


@pytest.mark.parametrize("addr", ["127.0.0.1", "localhost", "::1"])
def test_warn_only_on_loopback(auth, addr):
    level, message = auth.auth_startup_report(addr)
    assert level == "warn"
    assert "UNAUTHENTICATED" in message


def test_insecure_override_downgrades_refuse_to_warn(auth, monkeypatch):
    monkeypatch.setenv("FOURD_ALLOW_INSECURE", "1")
    level, message = auth.auth_startup_report("0.0.0.0")
    assert level == "warn"
    assert "FOURD_ALLOW_INSECURE" in message


def test_key_takes_precedence_over_insecure(auth, monkeypatch):
    monkeypatch.setenv("FOURD_API_KEY", "s3cret")
    monkeypatch.setenv("FOURD_ALLOW_INSECURE", "1")
    level, _ = auth.auth_startup_report("0.0.0.0")
    assert level == "ok"


def test_is_loopback_rejects_public_ip(auth):
    assert auth._is_loopback("0.0.0.0") is False
    assert auth._is_loopback("10.0.0.5") is False
    assert auth._is_loopback("127.0.0.1") is True
