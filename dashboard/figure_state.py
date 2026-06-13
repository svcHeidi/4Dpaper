"""Shared helpers for dashboard preview-state and figure parsing."""
from __future__ import annotations

import json
import re
from pathlib import Path

_SAFE_FIG_ID = re.compile(r"^[A-Za-z0-9_-]+$")

VALID_COLORMAPS = frozenset(
    {
        "coolwarm",
        "viridis",
        "plasma",
        "inferno",
        "magma",
        "turbo",
        "jet",
        "hot",
        "bwr",
        "RdBu",
        "rainbow",
        "Blues",
        "Greens",
        "Reds",
        "Oranges",
        "Purples",
        "YlOrRd",
        "RdYlBu",
        "Spectral",
        "PiYG",
        "seismic",
        "cividis",
        "bone",
        "copper",
        "gray",
        "pink",
    }
)


def is_safe_fig_id(fig_id: str) -> bool:
    """Return `True` when `fig_id` is safe for state-file names."""
    return bool(_SAFE_FIG_ID.fullmatch(fig_id))


def preview_state_path(project_root: Path, prefix: str, fig_id: str) -> Path:
    """Return the preview-state path for one figure."""
    return project_root / "state" / f"preview_{prefix}_{fig_id}.json"


def load_json_state(path: Path) -> dict:
    """Load a JSON state file or return `{}`."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def merge_preview_state(path: Path, payload: dict) -> dict:
    """Merge `payload` into on-disk preview state."""
    merged = load_json_state(path)
    merged.update(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2))
    return merged


def validate_colormap_payload(body: dict) -> dict[str, str]:
    """Filter a JSON payload down to valid field->colormap mappings."""
    payload: dict[str, str] = {}
    for field_name, cmap_name in body.items():
        if not isinstance(field_name, str) or not isinstance(cmap_name, str):
            continue
        if cmap_name not in VALID_COLORMAPS:
            continue
        payload[field_name] = cmap_name
    return payload


def validate_field_payload(body: dict) -> dict[str, str]:
    """Filter a JSON payload down to supported figure field/time state."""
    payload: dict[str, str] = {}
    if "field" in body:
        payload["field"] = str(body["field"])
    if "time" in body:
        payload["time"] = str(body["time"])
    return payload


def parse_4d_image_figures(qmd_path: Path) -> list[dict]:
    """
    Parse 4d-image shortcodes from a QMD.

    Returns a list of {"id": str, "fields": [str, ...]} dicts. Figures with
    no fields are omitted.
    """
    if not qmd_path.exists():
        return []
    text = re.sub(r"```.*?```", "", qmd_path.read_text(), flags=re.DOTALL)
    pattern = r"\{\{<\s*4d-image\s+(.*?)\s*>\}\}"
    figures: list[dict] = []
    seen: set[str] = set()

    for match in re.finditer(pattern, text, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)=["\'](.*?)["\']', raw):
            kwargs[key] = val
        fig_id = kwargs.get("id", "")
        if not fig_id or fig_id in seen:
            continue
        seen.add(fig_id)

        fields: list[str] = []
        if kwargs.get("field"):
            fields.append(kwargs["field"])
        for field in kwargs.get("fields", "").split(","):
            field = field.strip()
            if field and field not in fields:
                fields.append(field)
        if fields:
            figures.append({"id": fig_id, "fields": fields})

    return figures
