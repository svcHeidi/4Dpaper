from __future__ import annotations
import re
import json
import sys

def parse_video_shortcodes(text: str) -> list[dict]:
    """Parse `4d-video` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-video\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("fps", "10")
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        kwargs.setdefault("stride", "1")
        results.append(kwargs)
    return results

def parse_shortcodes(text: str) -> list[dict]:
    """Parse `4d-image` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)

    pattern = r'\{\{<\s*4d-image\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("field", "")
        kwargs.setdefault("fields", "")
        kwargs.setdefault("style", "")
        kwargs.setdefault("decimate", "auto")
        kwargs.setdefault("stride", "1")
        results.append(kwargs)
    return results

def parse_panel_shortcodes(text: str) -> list[dict]:
    """Parse `4d-panel` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-panel\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs:
            print("Warning: 4d-panel shortcode missing 'id' — skipping.", file=sys.stderr)
            continue
        subfigures = []
        n = 1
        while f"src{n}" in kwargs:
            subfigures.append({
                "src":    kwargs[f"src{n}"],
                "id":     kwargs.get(f"id{n}", f"panel-sub-{n}"),
                "field":  kwargs.get(f"field{n}", ""),
                "time":   kwargs.get(f"time{n}", "mid"),
                "fields": kwargs.get(f"fields{n}", ""),
            })
            n += 1
        if not subfigures:
            print(f"Warning: 4d-panel '{kwargs['id']}' has no sub-figures — skipping.", file=sys.stderr)
            continue
        results.append({
            "id":          kwargs["id"],
            "layout":      kwargs.get("layout", "1x1"),
            "height":      kwargs.get("height", "800px"),
            "caption":     kwargs.get("caption", ""),
            "camera_mode": kwargs.get("camera", "independent"),
            "subfigures":  subfigures,
        })
    return results

def parse_timeseries_shortcodes(text: str) -> list[dict]:
    """Parse `4d-timeseries` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-timeseries\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs:
            print("Warning: 4d-timeseries shortcode missing 'id' — skipping.", file=sys.stderr)
            continue
        if "src" not in kwargs:
            print("Warning: 4d-timeseries shortcode missing 'src' — skipping.", file=sys.stderr)
            continue
        results.append({
            "id":          kwargs["id"],
            "layout":      None,
            "height":      kwargs.get("height", "400px"),
            "caption":     kwargs.get("caption", ""),
            "camera_mode": "sync",
            "timeseries":  True,
            "src":         kwargs["src"],
            "field":       kwargs.get("field", ""),
            "steps":       kwargs.get("steps", "4"),
            "times":       kwargs.get("times", ""),
            "subfigures":  [],
        })
    return results

def parse_graph_shortcodes(text: str) -> list[dict]:
    """Parse `4d-graph` shortcodes from QMD text."""
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-graph\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src" not in kwargs:
            continue
        kwargs.setdefault("caption", "")
        results.append(kwargs)
    return results

def parse_multi_image_shortcodes(text: str) -> list[dict]:
    """Parse ``4d-multi-image`` shortcodes from QMD text.

    Attributes src1/field1, src2/field2, … (up to 8 sources) plus shared
    attributes: id, time, stride, caption.  Per-source overrides: cmap1/cmap2,
    decimate1/decimate2, line_width2 (auto-detected but overridable).
    """
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    pattern = r'\{\{<\s*4d-multi-image\s+(.*?)\s*>\}\}'
    results = []
    for match in re.finditer(pattern, stripped, re.DOTALL):
        raw = match.group(1)
        kwargs: dict[str, str] = {}
        for key, val in re.findall(r'(\w+)\s*=\s*["\'](.*?)["\']', raw):
            kwargs[key] = val
        if "id" not in kwargs or "src1" not in kwargs:
            continue
        kwargs.setdefault("time", "mid")
        kwargs.setdefault("stride", "1")
        kwargs.setdefault("caption", "")
        results.append(kwargs)
    return results

