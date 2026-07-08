"""Post-render figure injection produces a self-contained single HTML file.

The exported standalone HTML must inline each figure as an iframe `srcdoc`
(not reference an external sibling file), so it renders when shared on its own.
"""

import importlib
import sys
from pathlib import Path

import pytest

_EXT_DIR = Path(__file__).resolve().parents[1] / "_extensions" / "4dpaper"


@pytest.fixture
def inject(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("FOURD_APP_MODE", raising=False)
    monkeypatch.syspath_prepend(str(_EXT_DIR))
    import inject_figures

    return importlib.reload(inject_figures)


def _setup(tmp_path, figure_html: str, doc_html: str) -> Path:
    out = tmp_path / "_output"
    out.mkdir()
    figs = tmp_path / "state" / "figures"
    figs.mkdir(parents=True)
    (figs / "fig1.html").write_text(figure_html, encoding="utf-8")
    doc = out / "main-standalone.html"
    doc.write_text(doc_html, encoding="utf-8")
    return doc


def test_figure_inlined_as_srcdoc(inject, tmp_path):
    doc = _setup(
        tmp_path,
        '<html><body>UNIQUE_FIGURE_MARKER</body></html>',
        '<iframe data-fourd-inject="state/figures/fig1.html"></iframe>',
    )
    assert inject.main() == 0
    result = doc.read_text(encoding="utf-8")

    assert 'srcdoc="' in result
    assert "data-fourd-inject=" not in result  # placeholder consumed
    assert "UNIQUE_FIGURE_MARKER" in result  # content embedded
    # No external sibling copy is created — the file stands alone.
    assert not (tmp_path / "_output" / "state" / "figures" / "fig1.html").exists()


def test_special_characters_are_escaped(inject, tmp_path):
    doc = _setup(
        tmp_path,
        '<html><body>a & b attr="q" <b>x</b></body></html>',
        '<iframe data-fourd-inject="state/figures/fig1.html"></iframe>',
    )
    assert inject.main() == 0
    result = doc.read_text(encoding="utf-8")

    # Ampersands and quotes inside srcdoc must be entity-escaped so the
    # attribute (and the surrounding document) stays well-formed.
    assert "&amp;" in result
    assert "&quot;" in result


def test_missing_figure_marks_failure(inject, tmp_path):
    doc = _setup(
        tmp_path,
        "<html></html>",
        '<iframe data-fourd-inject="state/figures/does_not_exist.html"></iframe>',
    )
    assert inject.main() == 0
    result = doc.read_text(encoding="utf-8")
    assert 'data-fourd-inject-failed="true"' in result


def test_app_mode_skips_injection(inject, tmp_path, monkeypatch):
    monkeypatch.setenv("FOURD_APP_MODE", "1")
    doc = _setup(
        tmp_path,
        "<html><body>X</body></html>",
        '<iframe data-fourd-inject="state/figures/fig1.html"></iframe>',
    )
    assert inject.main() == 0
    # Untouched: the interactive app render keeps its own server-served figures.
    assert "data-fourd-inject=" in doc.read_text(encoding="utf-8")
