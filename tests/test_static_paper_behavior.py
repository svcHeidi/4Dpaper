"""Static papers must not call authoring-only persistence APIs."""
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_inline_relay_disables_persistence_outside_output_route():
    lua = (ROOT / "_extensions" / "4dpaper" / "shortcodes.lua").read_text(
        encoding="utf-8"
    )

    assert "var _CAN_PERSIST = /(^|\\/)output\\//" in lua
    assert "if (_CAN_PERSIST) return fetch(url, options);" in lua
    assert "if(_persist){fetch(\"/camera-lock/\"+PID)" in lua
    assert "if(_persist)fetch(\"/camera-lock/\"+PID" in lua


def test_asset_relay_matches_static_persistence_policy():
    relay = (ROOT / "_extensions" / "4dpaper" / "assets" / "relay.js").read_text(
        encoding="utf-8"
    )

    assert "var _CAN_PERSIST = /(^|\\/)output\\//" in relay
    assert "if (_CAN_PERSIST) return fetch(url, options);" in relay
    assert "_persist('/camera/'+camId" in relay
    assert "_persist('/field/'+figId2" in relay
