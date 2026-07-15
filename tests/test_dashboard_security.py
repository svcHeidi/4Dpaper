"""Static regressions for same-origin UI rendering of workspace-controlled names."""
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_workspace_names_are_rendered_as_text_not_html():
    html = (ROOT / "dashboard" / "static" / "index.html").read_text(encoding="utf-8")

    assert 'labelEl.innerHTML = `' not in html
    assert 'item.innerHTML = `' not in html
    assert '<span>${tab.name}</span>' not in html
    assert 'qmds.map(f =>' not in html
    assert 'document.createTextNode(name)' in html
    assert 'paperName.textContent = name' in html
