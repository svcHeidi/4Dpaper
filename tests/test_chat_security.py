"""Static regression checks for safe rendering in the optional AI sidebar."""
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_chat_does_not_render_user_or_model_content_as_html():
    chat = (ROOT / "dashboard" / "static" / "js" / "chat.js").read_text(encoding="utf-8")

    assert "marked.parse" not in chat
    assert "bubble.innerHTML" not in chat
    assert "aiBubble.innerHTML" not in chat
    assert "bubble.textContent" in chat
    assert "aiBubble.textContent" in chat


def test_dashboard_no_longer_loads_marked_for_chat_rendering():
    html = (ROOT / "dashboard" / "static" / "index.html").read_text(encoding="utf-8")

    assert "marked.min.js" not in html
