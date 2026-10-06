"""The browser UI is static files served by the same app. These tests guard what cannot be seen in an API test:
every screen exists, nothing is loaded from a third party, and the XSS discipline (text nodes only) cannot regress."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

WEB = Path(__file__).resolve().parents[2] / "src" / "zeroentry" / "web"
PAGES = {p.stem for p in (WEB / "static" / "pages").glob("*.js")}


def test_every_navigation_target_has_a_screen():
    nav = re.findall(r"\['([a-z_]+)', '[^']+', ", (WEB / "static" / "app.js").read_text(encoding="utf-8"))
    assert nav and set(nav) <= PAGES, set(nav) - PAGES


def test_screens_are_served_and_unknown_ones_are_404(shared):
    client = TestClient(shared.app, raise_server_exceptions=False)
    assert client.get("/", follow_redirects=False).headers["location"] == "/app/dashboard"
    for page in sorted(PAGES):
        response = client.get(f"/app/{page}")
        assert response.status_code == 200 and "text/html" in response.headers["content-type"] and "/static/app.js" in response.text, page
    for bad in ("nope", "..%2f..%2fetc%2fpasswd", "a.b", "login.js"):
        assert client.get(f"/app/{bad}").status_code == 404, bad
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/pages/login.js").headers["content-type"].startswith(("text/javascript", "application/javascript"))
    assert client.get("/static/../pyproject.toml").status_code == 404


def test_the_shell_loads_nothing_from_third_parties_and_has_no_inline_script_or_style():
    html = (WEB / "shell.html").read_text(encoding="utf-8")
    assert not re.search(r"https?://", html)                                  # no CDN, no external font
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)                      # every script is an external same-origin file
    assert not re.search(r"\sstyle=|\son[a-z]+=", html)                        # no inline style attribute or event handler
    css = (WEB / "static" / "style.css").read_text(encoding="utf-8")
    assert not re.search(r"@import|url\(\s*['\"]?https?:", css)


def test_ui_code_never_builds_markup_from_data():
    """User-controlled text must only ever reach the page as a text node (the h() helper), so stored text cannot become markup."""
    banned = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\s*\(|new Function|setAttribute\(\s*['\"]on|srcdoc")
    offenders = [f"{p.relative_to(WEB)}: {m.group(0)}" for p in (WEB / "static").rglob("*.js")
                 for m in banned.finditer(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_responses_carry_the_strict_content_security_policy(shared):
    response = TestClient(shared.app).get("/app/login")
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp
