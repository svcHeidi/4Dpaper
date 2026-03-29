"""Tests for shared dashboard figure-state helpers."""
from __future__ import annotations

import json
from pathlib import Path

from dashboard.figure_state import (
    figure_state_path,
    is_safe_fig_id,
    load_json_state,
    merge_json_state,
    parse_4d_image_figures,
    validate_colormap_payload,
    validate_field_payload,
)


def test_is_safe_fig_id_accepts_simple_ids():
    assert is_safe_fig_id("fig-vm") is True
    assert is_safe_fig_id("fig_vm-01") is True


def test_is_safe_fig_id_rejects_path_traversal():
    assert is_safe_fig_id("../../etc/passwd") is False
    assert is_safe_fig_id("fig/vm") is False


def test_figure_state_path_builds_expected_location(tmp_path):
    path = figure_state_path(tmp_path, "color", "fig-vm")
    assert path == tmp_path / "state" / "color_fig-vm.json"


def test_load_json_state_returns_empty_dict_for_missing(tmp_path):
    assert load_json_state(tmp_path / "missing.json") == {}


def test_load_json_state_returns_empty_dict_for_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not-json")
    assert load_json_state(path) == {}


def test_merge_json_state_updates_existing_state(tmp_path):
    path = tmp_path / "state" / "field_fig-vm.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"field": "Vm"}))

    merged = merge_json_state(path, {"time": "10"})

    assert merged == {"field": "Vm", "time": "10"}
    assert json.loads(path.read_text()) == {"field": "Vm", "time": "10"}


def test_validate_colormap_payload_filters_invalid_entries():
    payload = validate_colormap_payload(
        {
            "Vm": "coolwarm",
            "At": "not-a-cmap",
            "bad": 123,
        }
    )
    assert payload == {"Vm": "coolwarm"}


def test_validate_field_payload_keeps_only_supported_keys():
    payload = validate_field_payload(
        {
            "field": "Vm",
            "time": 5,
            "other": "ignored",
        }
    )
    assert payload == {"field": "Vm", "time": "5"}


def test_parse_4d_image_figures_collects_unique_fields(tmp_path):
    qmd = tmp_path / "paper.qmd"
    qmd.write_text(
        '\n'.join(
            [
                '{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}',
                '{{< 4d-image src="case.foam" field="Vm" fields="Vm,activationTime" id="fig-vm-2" >}}',
            ]
        )
    )

    figures = parse_4d_image_figures(qmd)

    assert figures == [
        {"id": "fig-vm", "fields": ["Vm"]},
        {"id": "fig-vm-2", "fields": ["Vm", "activationTime"]},
    ]


def test_parse_4d_image_figures_ignores_fenced_examples(tmp_path):
    qmd = tmp_path / "paper.qmd"
    qmd.write_text(
        "```md\n"
        '{{< 4d-image src="case.foam" field="Vm" id="skip-me" >}}\n'
        "```\n"
        '{{< 4d-image src="case.foam" field="Vm" id="use-me" >}}\n'
    )

    figures = parse_4d_image_figures(qmd)

    assert figures == [{"id": "use-me", "fields": ["Vm"]}]
