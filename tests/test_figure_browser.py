"""Tests for dashboard/figure_browser.py helper functions."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.figure_browser import (
    copy_case_data,
    find_foam_files,
    generate_shortcode,
    get_timesteps,
)


class TestFindFoamFiles:
    def test_finds_foam_in_directory(self, tmp_path):
        (tmp_path / "case.foam").write_text("")
        result = find_foam_files(tmp_path)
        assert len(result) == 1
        assert result[0].name == "case.foam"

    def test_finds_nested_foam_files(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "a.foam").write_text("")
        (tmp_path / "b.foam").write_text("")
        result = find_foam_files(tmp_path)
        assert len(result) == 2

    def test_returns_empty_for_missing_dir(self, tmp_path):
        result = find_foam_files(tmp_path / "nonexistent")
        assert result == []

    def test_ignores_non_foam_files(self, tmp_path):
        (tmp_path / "mesh.vtk").write_text("")
        (tmp_path / "case.foam").write_text("")
        result = find_foam_files(tmp_path)
        assert len(result) == 1

    def test_returns_sorted(self, tmp_path):
        for name in ("z.foam", "a.foam", "m.foam"):
            (tmp_path / name).write_text("")
        result = find_foam_files(tmp_path)
        names = [f.name for f in result]
        assert names == sorted(names)


class TestGetTimesteps:
    def test_finds_timesteps_in_processor0(self, tmp_path):
        proc0 = tmp_path / "processor0"
        proc0.mkdir()
        for ts in ("0.005", "0.01", "0.05"):
            (proc0 / ts).mkdir()
        # non-numeric directories should be ignored
        (proc0 / "constant").mkdir()
        result = get_timesteps(tmp_path)
        assert result == ["0.005", "0.01", "0.05"]

    def test_falls_back_to_serial_case(self, tmp_path):
        for ts in ("1", "2", "10"):
            (tmp_path / ts).mkdir()
        result = get_timesteps(tmp_path)
        assert result == ["1", "2", "10"]

    def test_returns_empty_when_no_timesteps(self, tmp_path):
        result = get_timesteps(tmp_path)
        assert result == []

    def test_sorts_numerically_not_lexicographically(self, tmp_path):
        proc0 = tmp_path / "processor0"
        proc0.mkdir()
        for ts in ("0.01", "0.005", "0.1"):
            (proc0 / ts).mkdir()
        result = get_timesteps(tmp_path)
        assert result == ["0.005", "0.01", "0.1"]


class TestGenerateShortcode:
    def test_basic_shortcode(self):
        sc = generate_shortcode(
            src="case.foam", field="Vm", fig_id="fig-vm", time="mid", caption=""
        )
        assert sc == '{{< 4d-image src="case.foam" field="Vm" id="fig-vm" >}}'

    def test_time_mid_is_omitted(self):
        sc = generate_shortcode(
            src="case.foam", field="Vm", fig_id="fig-vm", time="mid", caption=""
        )
        assert 'time=' not in sc

    def test_non_mid_time_is_included(self):
        sc = generate_shortcode(
            src="case.foam", field="Vm", fig_id="fig-vm", time="last", caption=""
        )
        assert 'time="last"' in sc

    def test_specific_timestep_included(self):
        sc = generate_shortcode(
            src="case.foam", field="Vm", fig_id="fig-vm", time="0.025", caption=""
        )
        assert 'time="0.025"' in sc

    def test_caption_included_when_set(self):
        sc = generate_shortcode(
            src="case.foam", field="Vm", fig_id="fig-vm", time="mid",
            caption="My figure caption"
        )
        assert 'caption="My figure caption"' in sc

    def test_empty_caption_omitted(self):
        sc = generate_shortcode(
            src="case.foam", field="Vm", fig_id="fig-vm", time="mid", caption="  "
        )
        assert "caption=" not in sc

    def test_src_included(self):
        sc = generate_shortcode(
            src="/path/to/Niederer.foam", field="Vm", fig_id="fig-vm",
            time="mid", caption=""
        )
        assert 'src="/path/to/Niederer.foam"' in sc

    def test_shortcode_wrapping(self):
        sc = generate_shortcode(
            src="x.foam", field="Vm", fig_id="fig-vm", time="mid", caption=""
        )
        assert sc.startswith("{{< 4d-image ")
        assert sc.endswith(" >}}")


class TestCopyCaseData:
    def _make_case(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create a minimal fake OpenFOAM parallel case, return (foam_path, case_root)."""
        case_root = tmp_path / "MyCase"
        case_root.mkdir()
        foam = case_root / "MyCase.foam"
        foam.write_text("")

        # constant/polyMesh (serial mesh — optional)
        (case_root / "constant" / "polyMesh").mkdir(parents=True)
        (case_root / "constant" / "polyMesh" / "points").write_text("points data")

        # Two processor directories with timesteps
        for p in ("processor0", "processor1"):
            proc = case_root / p
            (proc / "constant" / "polyMesh").mkdir(parents=True)
            (proc / "constant" / "polyMesh" / "owner").write_text("owner data")
            for ts in ("0.005", "0.01"):
                ts_dir = proc / ts
                ts_dir.mkdir()
                (ts_dir / "Vm").write_text("field data")

        return foam, case_root

    def test_copies_foam_marker(self, tmp_path):
        foam, _ = self._make_case(tmp_path)
        dest = tmp_path / "dest"
        log: list[str] = []
        new_foam = copy_case_data(foam, dest, log)
        assert new_foam.exists()
        assert new_foam.name == "MyCase.foam"

    def test_copies_serial_mesh(self, tmp_path):
        foam, _ = self._make_case(tmp_path)
        dest = tmp_path / "dest"
        copy_case_data(foam, dest, [])
        assert (dest / "MyCase" / "constant" / "polyMesh" / "points").exists()

    def test_copies_processor_mesh(self, tmp_path):
        foam, _ = self._make_case(tmp_path)
        dest = tmp_path / "dest"
        copy_case_data(foam, dest, [])
        assert (dest / "MyCase" / "processor0" / "constant" / "polyMesh" / "owner").exists()
        assert (dest / "MyCase" / "processor1" / "constant" / "polyMesh" / "owner").exists()

    def test_copies_timestep_fields(self, tmp_path):
        foam, _ = self._make_case(tmp_path)
        dest = tmp_path / "dest"
        copy_case_data(foam, dest, [])
        assert (dest / "MyCase" / "processor0" / "0.005" / "Vm").exists()
        assert (dest / "MyCase" / "processor1" / "0.01" / "Vm").exists()

    def test_returns_correct_foam_path(self, tmp_path):
        foam, _ = self._make_case(tmp_path)
        dest = tmp_path / "dest"
        result = copy_case_data(foam, dest, [])
        assert result == dest / "MyCase" / "MyCase.foam"

    def test_logs_copied_items(self, tmp_path):
        foam, _ = self._make_case(tmp_path)
        dest = tmp_path / "dest"
        log: list[str] = []
        copy_case_data(foam, dest, log)
        joined = "\n".join(log)
        assert "MyCase.foam" in joined
        assert "processor0" in joined

    def test_overwrites_existing_destination(self, tmp_path):
        foam, _ = self._make_case(tmp_path)
        dest = tmp_path / "dest"
        copy_case_data(foam, dest, [])
        # Second call should not raise even though dest already exists
        copy_case_data(foam, dest, [])
        assert (dest / "MyCase" / "MyCase.foam").exists()
