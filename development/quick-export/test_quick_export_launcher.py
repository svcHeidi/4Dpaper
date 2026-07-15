"""Development checks for the isolated Quick Export launcher."""
from __future__ import annotations

import subprocess
import importlib.util
from pathlib import Path

import pytest

import serve


DEV_ROOT = Path(__file__).parent
ROOT = DEV_ROOT.parent.parent


def _load_backend():
    path = DEV_ROOT / "backend_handlers.py"
    spec = importlib.util.spec_from_file_location("quick_export_test_backend", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quick_launcher_uses_disposable_workspace_and_read_only_source():
    text = (DEV_ROOT / "4d-quick.sh").read_text(encoding="utf-8")

    assert 'RUNTIME_WORKSPACE=$(mktemp -d ' in text
    assert 'QUICK_TARGET="/workspace/source/${BASENAME}"' in text
    assert '-p      "127.0.0.1:${PORT}:5006"' in text
    assert '-v      "${RUNTIME_WORKSPACE}:/workspace"' in text
    assert '-v      "${SOURCE_ROOT}:/workspace/source:ro"' in text
    assert '-v      "${OUTPUT_DIR}:/quick-output"' in text
    assert ':/app:ro' not in text
    assert '-e      "FOURD_ALLOW_INSECURE=1"' in text
    assert '-e      "FOURD_QUICK_TARGET=${QUICK_TARGET}"' in text
    assert '-e      "FOURD_QUICK_OUTPUT=/quick-output"' in text


def test_quick_launcher_cleans_workspace_and_retains_only_html_output_mount():
    text = (DEV_ROOT / "4d-quick.sh").read_text(encoding="utf-8")

    assert 'rm -rf "$RUNTIME_WORKSPACE"' in text
    assert 'FOURD_UNSAFE_QUICK_EXPORT' not in text
    assert '--output-dir|-o' in text
    assert 'output directory must be dedicated and must not contain the source' in text
    assert 'output directory must not be inside the read-only source case' in text


def test_quick_launcher_has_valid_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", str(DEV_ROOT / "4d-quick.sh")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_quick_html_is_kept_out_of_the_production_static_tree():
    assert (DEV_ROOT / "quick.html").exists()
    assert not (ROOT / "dashboard" / "static" / "quick.html").exists()
    server = (ROOT / "serve.py").read_text(encoding="utf-8")
    assert 'if not os.getenv("FOURD_QUICK_TARGET", "").strip()' in server
    assert 'root / "development" / "quick-export" / "backend_handlers.py"' in server


def test_quick_html_does_not_load_ai_frontend():
    text = (DEV_ROOT / "quick.html").read_text(encoding="utf-8").lower()

    assert "chat.js" not in text
    assert "/api/agents" not in text
    assert "model" not in text
    assert "provider" not in text


def test_quick_export_uses_main_app_standalone_html_pipeline():
    backend = (DEV_ROOT / "backend_handlers.py").read_text(encoding="utf-8")
    frontend = (DEV_ROOT / "quick.html").read_text(encoding="utf-8")

    assert 'run_quarto_render, qmd_path, log_lines, "html-export", None' in backend
    assert "_validate_standalone_html_output(html_path)" in backend
    assert 'self.set_header("Content-Type", "text/html; charset=utf-8")' in backend
    assert "zipfile.ZipFile" not in backend
    assert "application/zip" not in backend
    assert "data:text/html;base64" not in backend
    assert "_retain_html(figure_path" in backend
    assert "_retain_html(html_path" in backend
    assert "html_only=True" in backend
    assert "quick-export-standalone.html" in frontend


def test_image_bundles_only_the_opt_in_quick_module():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY development/quick-export /app/development/quick-export" in dockerfile


def test_normal_server_does_not_load_quick_routes(monkeypatch):
    monkeypatch.delenv("FOURD_QUICK_TARGET", raising=False)

    assert serve._load_opt_in_quick_routes(ROOT) == []


def test_explicit_quick_mode_loads_page_and_api_routes(monkeypatch, tmp_path):
    target = tmp_path / "case.vtu"
    target.write_bytes(b"fixture")
    monkeypatch.setenv("FOURD_QUICK_TARGET", str(target))

    routes = serve._load_opt_in_quick_routes(ROOT)
    patterns = [route[0] for route in routes]

    assert "/quick.html" in patterns
    assert "/api/quick-target" in patterns
    assert "/api/quick-init" in patterns
    assert "/api/quick-export" in patterns


def test_target_must_be_inside_temporary_workspace(monkeypatch, tmp_path):
    backend = _load_backend()
    project = tmp_path / "workspace"
    project.mkdir()
    inside = project / "source" / "case.vtu"
    inside.parent.mkdir()
    inside.write_bytes(b"fixture")
    outside = tmp_path / "outside.vtu"
    outside.write_bytes(b"fixture")

    monkeypatch.setenv("FOURD_QUICK_TARGET", str(inside))
    assert backend._resolve_quick_target(project) == inside

    monkeypatch.setenv("FOURD_QUICK_TARGET", str(outside))
    with pytest.raises(ValueError, match="temporary workspace"):
        backend._resolve_quick_target(project)


def test_retain_html_copies_only_named_html_artifact(monkeypatch, tmp_path):
    backend = _load_backend()
    source = tmp_path / "workspace" / "state" / "figures" / "fig-case.html"
    source.parent.mkdir(parents=True)
    source.write_text("<html>figure</html>", encoding="utf-8")
    output = tmp_path / "retained"
    output.mkdir()
    monkeypatch.setenv("FOURD_QUICK_OUTPUT", str(output))

    retained = backend._retain_html(source, "fig-case.html")

    assert retained.read_text(encoding="utf-8") == "<html>figure</html>"
    assert sorted(path.name for path in output.iterdir()) == ["fig-case.html"]
    assert not list(output.glob(".*.tmp"))

    with pytest.raises(ValueError, match="filename"):
        backend._retain_html(source, "../escape.html")


def test_export_filename_is_ascii_and_shortcode_values_are_unambiguous():
    backend = _load_backend()

    assert backend._safe_html_stem("Simulação cardíaca") == "Simulacao-cardiaca"
    assert backend._shortcode_attribute("field", "pressure") == 'field="pressure"'
    with pytest.raises(ValueError, match="unsupported"):
        backend._shortcode_attribute("field", 'bad"field')
