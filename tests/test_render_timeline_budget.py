"""Tests for heavy-figure timeline frame budgeting."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_extensions" / "4dpaper"))


def _load_render_module():
    return importlib.import_module("lib.render")


def test_timeline_budget_leaves_small_sequences_unchanged():
    mod = _load_render_module()

    original = [0, 8, 16, 24]
    capped, max_frames = mod._apply_timeline_frame_budget(original, point_budget=10_000)

    assert capped == original
    assert max_frames is None


def test_timeline_budget_caps_extreme_payloads_to_five_frames():
    mod = _load_render_module()

    original = list(range(0, 160, 8))
    capped, max_frames = mod._apply_timeline_frame_budget(original, point_budget=150_000)

    assert max_frames == mod._MAX_TIMELINE_FRAMES_EXTREME
    assert len(capped) == 5
    assert capped[0] == original[0]
    assert capped[-1] == original[-1]


def test_timeline_budget_preserves_order_after_rounding():
    mod = _load_render_module()

    original = [0, 8, 16, 24, 32, 40, 48, 56, 64]
    capped, _ = mod._apply_timeline_frame_budget(original, point_budget=90_000)

    assert capped == sorted(capped)
    assert len(capped) == len(set(capped))
