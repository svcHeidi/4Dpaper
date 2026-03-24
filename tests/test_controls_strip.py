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
        assert 'id="cs-pop-axes-fig_vm"' in html
        assert 'id="cs-pop-lock-fig_vm"' not in html

    def test_corner_cube_present_when_show_orientation(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        # SVG is now at fixed bottom-left, not inside popup
        assert 'id="cs-svg-axes-fig_vm"' in html
        assert "bottom:4px" in html
        assert "left:4px" in html

    def test_axes_popup_above_corner(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        # Popup anchored above the cube, not in the right-edge strip position
        assert 'id="cs-pop-axes-fig_vm"' in html
        assert "bottom:36px" in html

    def test_corner_cube_absent_when_orientation_hidden(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=False)
        assert 'id="cs-svg-axes-fig_vm"' not in html
        assert 'id="cs-corner-fig_vm"' not in html

    def test_lock_widget_present_when_show_lock(self):
        """cs-lock-widget at top:4px;right:4px when show_lock_btn=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'id="cs-lock-widget-fig_vm"' in html
        assert "top:4px" in html
        assert "right:4px" in html

    def test_lock_widget_absent_when_hide(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=False)
        assert 'id="cs-lock-widget-fig_vm"' not in html

    def test_lock_badge_present_when_show_lock(self):
        """Badge element present and starts hidden when show_lock_btn=True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        assert 'id="cs-lock-badge-fig_vm"' in html
        assert "display:none" in html

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

    def test_interactor_enabled_on_open(self):
        """`setEnabled(1)` present inside _openRotation."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "setEnabled(1)" in html

    def test_null_interactor_safe(self):
        """Both _openRotation and _closeRotation guard with if(_iact)."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        assert "if(_iact)_iact.setEnabled(1)" in js or ("_openRotation" in js and "if(_iact)" in js)
        assert "if(_iact)_iact.setEnabled(0)" in js or ("_closeRotation" in js and "if(_iact)" in js)

    def test_click_handler_on_svg(self):
        """SVG click listener wired to open/close rotation popup."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert 'cs-svg-axes-fig_vm' in html
        assert 'addEventListener("click"' in html or "addEventListener('click'" in html

    def test_preset_closes_popup(self):
        """_closeRotation() must appear inside csSetView_ function body."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        # Find the csSetView_ function and confirm _closeRotation() is inside it
        start = js.find("csSetView_fig_vm")
        assert start != -1, "csSetView_ not found"
        func_body = js[start:start + 1200]
        assert "_closeRotation()" in func_body, "_closeRotation() not inside csSetView_"

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
        """if(_locked) guard appears before _CS_ALL loop in csToggle_."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_lock_btn=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        toggle_start = js.find("csToggle_fig_vm")
        assert toggle_start != -1, "csToggle_ not found"
        func_region = js[toggle_start:toggle_start + 300]
        locked_pos = func_region.find("if(_locked)")
        cs_all_pos = func_region.find("_CS_ALL")
        assert locked_pos != -1, "if(_locked) not in csToggle_"
        assert cs_all_pos != -1, "_CS_ALL not in csToggle_"
        assert locked_pos < cs_all_pos, "if(_locked) must come before _CS_ALL loop"

    def test_corner_cube_checks_locked_flag(self):
        """SVG click listener contains if(_locked) when both flags True."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=True)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        svg_var_pos = js.find('getElementById("cs-svg-axes-fig_vm")')
        assert svg_var_pos != -1
        listener_region = js[svg_var_pos:svg_var_pos + 400]
        assert "if(_locked)" in listener_region

    def test_corner_cube_no_locked_gate_when_lock_hidden(self):
        """SVG click listener has NO if(_locked) when show_lock_btn=False."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True, show_lock_btn=False)
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        svg_var_pos = js.find('getElementById("cs-svg-axes-fig_vm")')
        assert svg_var_pos != -1
        listener_region = js[svg_var_pos:svg_var_pos + 400]
        assert "if(_locked)" not in listener_region

    def test_render_before_debounce(self):
        """renderWindow.render() fires before setTimeout in time slider handler."""
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet(
            "fig-vm",
            time_labels=["0.0", "0.5"], time_data_b64=["AA==", "BB=="],
            time_global_range=[0.0, 1.0], time_field="Vm",
        )
        js = html.split("<script>", 1)[1] if "<script>" in html else html
        slider_pos = js.find("_tSlider")
        assert slider_pos != -1
        slider_section = js[slider_pos:slider_pos + 800]
        render_pos = slider_section.find("renderWindow.render()")
        settimeout_pos = slider_section.find("setTimeout")
        assert render_pos != -1, "renderWindow.render() not in slider handler"
        assert settimeout_pos != -1, "setTimeout not in slider handler"
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

    def test_preset_buttons_call_set_view(self):
        mod = _load_4dpaper()
        html = mod._controls_strip_snippet("fig-vm", show_orientation=True)
        assert "csSetView_fig_vm('iso')" in html or 'csSetView_fig_vm("iso")' in html

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
