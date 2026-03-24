"""Tests for the unified controls strip snippet."""
from __future__ import annotations
import importlib.util
from pathlib import Path


def _load_4dpaper():
    spec = importlib.util.spec_from_file_location(
        "fourDpaper",
        Path(__file__).parent.parent / "_extensions" / "4dpaper" / "4dpaper.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestControlsStripExists:
    def test_function_exists(self):
        mod = _load_4dpaper()
        assert hasattr(mod, "_controls_strip_snippet")

    def test_returns_string(self):
        mod = _load_4dpaper()
        result = mod._controls_strip_snippet("fig-vm")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_empty_when_all_hidden(self):
        mod = _load_4dpaper()
        result = mod._controls_strip_snippet(
            "fig-vm", show_lock_btn=False, show_orientation=False
        )
        assert result == ""


class TestControlsStripHtml:
    def test_strip_div_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", show_lock_btn=True,
            fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0, 1], "at": [0, 1]},
        )
        assert 'id="cs-strip-fig_vm"' in html

    def test_lock_button_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert 'id="cs-btn-lock-fig_vm"' not in html

    def test_axes_button_absent_when_show_orientation(self):
        """Axes strip button is replaced by corner cube — must be absent."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-btn-axes-fig_vm"' not in html

    def test_axes_button_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'id="cs-btn-axes-fig_vm"' not in html

    def test_field_button_present_when_multiple_fields(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert 'id="cs-btn-field-fig_vm"' in html

    def test_field_button_absent_when_single_field(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm"], active_field="Vm",
            field_data_b64={"Vm": "AA=="}, field_ranges={"Vm": [0,1]},
        )
        assert 'id="cs-btn-field-fig_vm"' not in html

    def test_time_button_present_when_time_data(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.0", "0.5"], time_data_b64=["AA==", "BB=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        assert 'id="cs-btn-time-fig_vm"' in html

    def test_time_button_absent_when_no_time(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert 'id="cs-btn-time-fig_vm"' not in html

    def test_popup_panels_present_for_active_features(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True, show_orientation=True)
        # axes popup gone — must be absent
        assert 'id="cs-pop-axes-fig_vm"' not in html
        # lock popup still gone
        assert 'id="cs-pop-lock-fig_vm"' not in html
        # corner cube div must be present
        assert 'id="cs-corner-fig_vm"' in html

    def test_corner_cube_present_when_show_orientation(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-svg-axes-fig_vm"' in html
        assert 'width="72"' in html
        assert 'height="72"' in html

    def test_cube_svg_size(self):
        """Corner div position: fixed bottom-left when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        corner_pos = html.find('id="cs-corner-fig_vm"')
        assert corner_pos != -1, "cs-corner div not found"
        region = html[corner_pos:corner_pos + 200]
        assert "bottom:4px" in region
        assert "left:4px" in region

    def test_axes_popup_absent(self):
        """cs-pop-axes- must NOT be emitted when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-pop-axes-fig_vm"' not in html

    def test_corner_cube_absent_when_orientation_hidden(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'id="cs-svg-axes-fig_vm"' not in html
        assert 'id="cs-corner-fig_vm"' not in html

    def test_lock_widget_present_when_show_lock(self):
        """cs-lock-widget at top:4px;right:4px when show_lock_btn=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        widget_pos = html.find('id="cs-lock-widget-fig_vm"')
        assert widget_pos != -1, "cs-lock-widget element not found"
        widget_region = html[widget_pos:widget_pos + 120]
        assert "top:4px" in widget_region
        assert "right:4px" in widget_region

    def test_lock_widget_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert 'id="cs-lock-widget-fig_vm"' not in html

    def test_lock_badge_present_when_show_lock(self):
        """Badge element present and starts hidden (display:none) when show_lock_btn=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        badge_pos = html.find('id="cs-lock-badge-fig_vm"')
        assert badge_pos != -1, "cs-lock-badge element not found"
        badge_region = html[badge_pos:badge_pos + 80]
        assert "display:none" in badge_region

    def test_lock_badge_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert 'id="cs-lock-badge-fig_vm"' not in html

    def test_lock_popup_absent(self):
        """cs-pop-lock is no longer emitted."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'id="cs-pop-lock-fig_vm"' not in html

    def test_lock_button_absent_from_strip(self):
        """cs-btn-lock is no longer in the right strip."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'id="cs-btn-lock-fig_vm"' not in html

    def test_lock_widget_absent_show_lock_false_orientation_true(self):
        """No lock widget or badge when show_lock_btn=False, even with orientation."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False, show_orientation=True)
        assert 'id="cs-lock-widget-fig_vm"' not in html
        assert 'id="cs-lock-badge-fig_vm"' not in html

    def test_snippet_not_empty_when_only_orientation(self):
        """Corner cube alone is enough — snippet must not return '' when
        show_lock_btn=False and no fields/time but show_orientation=True."""
        mod = _load_4dpaper()
        result = mod._controls_strip_snippet("fig-vm", show_lock_btn=False, show_orientation=True)
        assert result != ""
        assert 'id="cs-svg-axes-fig_vm"' in result


class TestControlsStripJs:
    def test_toggle_function_defined(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "csToggle_fig_vm" in html

    def test_toggle_references_popup_ids(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "cs-pop-" in html

    def test_hyphens_replaced_in_js_identifier(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("ts-vm-0")
        assert "csToggle_ts_vm_0" in html
        assert "csToggle_ts-vm-0" not in html

    def test_locked_always_declared(self):
        """_locked must be declared even when show_lock_btn=False (used by _sendCam)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert "var _locked=false" in html or "var _locked = false" in html

    def test_iact_declared_at_top(self):
        """var _iact = null must be declared (show_orientation=True)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "var _iact=null" in html or "var _iact = null" in html

    def test_interactor_disabled_on_load(self):
        """setEnabled(0) injected into _wR callback when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "setEnabled(0)" in html

    def test_interactor_not_disabled_when_orientation_hidden(self):
        """No setEnabled(0) emitted when show_orientation=False (stays free)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert "setEnabled(0)" not in html

    def test_show_locked_badge_function_present(self):
        """_showLockedBadge emitted when show_lock_btn=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "_showLockedBadge" in html

    def test_show_locked_badge_absent_when_hide(self):
        """_showLockedBadge NOT emitted when show_lock_btn=False."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert "_showLockedBadge" not in html

    def test_set_locked_helper_present(self):
        """_setLocked helper emitted when show_lock_btn=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "_setLocked" in html

    def test_toggle_checks_locked_flag(self):
        """if(_locked) guard appears before _CS_ALL loop in csToggle_.
        Verifies ordering only; cannot verify it is a return guard from string inspection alone."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        toggle_start = js.find("csToggle_fig_vm")
        assert toggle_start != -1, "csToggle_ not found"
        func_region = js[toggle_start:toggle_start + 500]
        locked_pos = func_region.find("if(_locked)")
        cs_all_pos = func_region.find("_CS_ALL")
        assert locked_pos != -1, "if(_locked) not in csToggle_"
        assert cs_all_pos != -1, "_CS_ALL not in csToggle_"
        assert locked_pos < cs_all_pos, "if(_locked) must come before _CS_ALL loop"

    def test_draw_cube_function_present(self):
        """`_drawCube` emitted when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "_drawCube" in html

    def test_draw_cube_absent_when_orientation_hidden(self):
        """`_drawCube` NOT emitted when show_orientation=False."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert "_drawCube" not in html

    def test_cs_setview_accepts_direction_array(self):
        """`csSetView_` body normalises direction via `_n3(dir)`."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        start = js.find("csSetView_fig_vm")
        assert start != -1, "csSetView_ not found"
        func_body = js[start:start + 600]
        assert "_n3(dir)" in func_body, "_n3(dir) not in csSetView_ body"

    def test_interactor_enabled_on_setview(self):
        """`if(_iact)` guard and `setEnabled(1)` both inside csSetView_."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        start = js.find("csSetView_fig_vm")
        assert start != -1, "csSetView_ not found"
        func_body = js[start:start + 600]
        assert "if(_iact)" in func_body, "if(_iact) guard missing in csSetView_"
        assert "setEnabled(1)" in func_body, "setEnabled(1) missing in csSetView_"

    def test_open_rotation_absent(self):
        """`_openRotation` must NOT appear anywhere in the snippet."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "_openRotation" not in html

    def test_close_rotation_absent(self):
        """`_closeRotation` must NOT appear anywhere in the snippet."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "_closeRotation" not in html

    def test_close_on_toggle_absent(self):
        """`_close_on_toggle` interactor-gate logic must not be emitted.
        Detects: cs-pop-axes- referenced in JS (used to gate interactor on toggle)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        assert "cs-pop-axes-" not in js, \
            "cs-pop-axes- found in JS — _close_on_toggle still emitted"

    def test_cube_lock_gate_in_draw_cube(self):
        """`_showLockedBadge` present inside `_drawCube` when show_lock_btn=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        cube_start = js.find("function _drawCube")
        assert cube_start != -1, "_drawCube not found"
        cube_body = js[cube_start:cube_start + 2000]
        assert "_showLockedBadge" in cube_body, \
            "_showLockedBadge not found inside _drawCube with show_lock_btn=True"

    def test_cube_no_lock_gate_when_lock_hidden(self):
        """`_showLockedBadge` NOT present inside `_drawCube` when show_lock_btn=False."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=False)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        cube_start = js.find("function _drawCube")
        assert cube_start != -1, "_drawCube not found"
        cube_body = js[cube_start:cube_start + 2000]
        assert "_showLockedBadge" not in cube_body, \
            "_showLockedBadge found inside _drawCube with show_lock_btn=False"

    def test_render_before_debounce(self):
        """renderWindow.render() fires immediately; only postMessage is debounced."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.0", "0.5"], time_data_b64=["AA==", "BB=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        # Anchor to the input event listener, not the variable declaration
        input_handler_pos = js.find('addEventListener("input"')
        assert input_handler_pos != -1, "input event listener not found"
        handler_section = js[input_handler_pos:input_handler_pos + 600]
        render_pos = handler_section.find("renderWindow.render()")
        settimeout_pos = handler_section.find("setTimeout")
        assert render_pos != -1, "renderWindow.render() not in input handler"
        assert settimeout_pos != -1, "setTimeout not in input handler"
        assert render_pos < settimeout_pos, "renderWindow.render() must precede setTimeout"


class TestControlsStripCameraLogic:
    def test_camera_apply_listener_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "4dpaper-camera-apply" in html

    def test_camera_sets_position_focal_viewup(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "setPosition" in html
        assert "setFocalPoint" in html
        assert "setViewUp" in html

    def test_send_camera_on_pointerup(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm")
        assert "pointerup" in html

    def test_lock_toggle_sends_postmessage(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert "4dpaper-lock-toggle" in html


class TestControlsStripOrientationLogic:
    def test_axes_svg_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'id="cs-svg-axes-fig_vm"' in html

    def test_preset_view_function_defined(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "csSetView_fig_vm" in html

    def test_axes_raf_loop_present(self):
        """Axes rAF loop (_axLoop) must exist when show_orientation=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "_axLoop" in html

    def test_axes_raf_loop_absent_when_hidden(self):
        """When show_orientation=False, _axLoop must not be emitted."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert "_axLoop" not in html


class TestControlsStripFieldLogic:
    def test_field_select_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert 'id="cs-field-sel-fig_vm"' in html

    def test_field_data_embedded(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AABB", "at": "CCDD"}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert "AABB" in html
        assert "CCDD" in html

    def test_field_setdata_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm", fields_to_embed=["Vm", "at"], active_field="Vm",
            field_data_b64={"Vm": "AA==", "at": "AA=="}, field_ranges={"Vm": [0,1], "at": [0,1]},
        )
        assert "setData" in html
        assert "setScalarRange" in html


class TestControlsStripTimeLogic:
    def test_time_slider_present(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.0", "0.5", "1.0"], time_data_b64=["AA==", "BB==", "CC=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        assert 'id="cs-time-slider-fig_vm"' in html

    def test_time_labels_embedded(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.001", "0.005"], time_data_b64=["AA==", "BB=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        assert "0.001" in html
        assert "0.005" in html
