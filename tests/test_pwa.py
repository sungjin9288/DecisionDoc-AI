"""tests/test_pwa.py — Tests for PWA (Progressive Web App) support.

Coverage:
  Endpoints       : GET /manifest.json (200, content-type),
                    GET /sw.js (200, Service-Worker-Allowed header),
                    GET /offline.html (200, html),
                    GET /favicon.ico (200, image),
                    GET / (200, returns HTML)
  Manifest content: name, short_name, icons array, shortcuts, start_url,
                    display=standalone, categories
  sw.js content   : install/activate/fetch handlers present,
                    push + notificationclick handlers
  Static icons    : icon-192.png and icon-512.png exist as valid PNG files
  generate_icons  : script runs without error
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


# ── Client factory ─────────────────────────────────────────────────────────────


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app())


# ── Endpoint tests ─────────────────────────────────────────────────────────────


def test_root_returns_html(tmp_path, monkeypatch):
    """GET / should return the index.html (not a redirect)."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")


def test_root_disables_html_shell_cache(tmp_path, monkeypatch):
    """GET / should not let browsers keep stale admin HTML after deploys."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/")
    assert res.headers.get("cache-control") == "no-store"


def test_root_head_returns_html_headers(tmp_path, monkeypatch):
    """HEAD / should return 200 with HTML headers."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.head("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")


def test_manifest_json_endpoint_200(tmp_path, monkeypatch):
    """GET /manifest.json returns 200."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/manifest.json")
    assert res.status_code == 200


def test_manifest_json_content_type(tmp_path, monkeypatch):
    """GET /manifest.json returns application/manifest+json content-type."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/manifest.json")
    ct = res.headers.get("content-type", "")
    assert "manifest+json" in ct or "application/json" in ct


def test_manifest_json_head_returns_headers(tmp_path, monkeypatch):
    """HEAD /manifest.json returns 200 with manifest headers."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.head("/manifest.json")
    assert res.status_code == 200
    ct = res.headers.get("content-type", "")
    assert "manifest+json" in ct or "application/json" in ct


def test_sw_js_endpoint_200(tmp_path, monkeypatch):
    """GET /sw.js returns 200."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/sw.js")
    assert res.status_code == 200


def test_sw_js_service_worker_allowed_header(tmp_path, monkeypatch):
    """GET /sw.js includes Service-Worker-Allowed: / header."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/sw.js")
    assert res.headers.get("service-worker-allowed") == "/"


def test_sw_js_disables_http_cache(tmp_path, monkeypatch):
    """GET /sw.js should revalidate so new deployment workers activate quickly."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/sw.js")
    assert res.headers.get("cache-control") == "no-cache"


def test_sw_js_javascript_content_type(tmp_path, monkeypatch):
    """GET /sw.js returns application/javascript content-type."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/sw.js")
    assert "javascript" in res.headers.get("content-type", "")


def test_sw_js_head_returns_headers(tmp_path, monkeypatch):
    """HEAD /sw.js returns 200 with service worker headers."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.head("/sw.js")
    assert res.status_code == 200
    assert "javascript" in res.headers.get("content-type", "")
    assert res.headers.get("service-worker-allowed") == "/"


def test_offline_html_endpoint_200(tmp_path, monkeypatch):
    """GET /offline.html returns 200."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/offline.html")
    assert res.status_code == 200


def test_offline_html_is_html(tmp_path, monkeypatch):
    """GET /offline.html returns text/html content-type."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/offline.html")
    assert "text/html" in res.headers.get("content-type", "")


def test_offline_html_head_returns_headers(tmp_path, monkeypatch):
    """HEAD /offline.html returns 200 with HTML headers."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.head("/offline.html")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")


def test_favicon_endpoint_200(tmp_path, monkeypatch):
    """GET /favicon.ico returns 200."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/favicon.ico")
    assert res.status_code == 200


def test_favicon_is_image(tmp_path, monkeypatch):
    """GET /favicon.ico returns an image content-type."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/favicon.ico")
    assert res.headers.get("content-type", "").startswith("image/")


def test_favicon_head_returns_headers(tmp_path, monkeypatch):
    """HEAD /favicon.ico returns 200 with image headers."""
    client = _make_client(tmp_path, monkeypatch)
    res = client.head("/favicon.ico")
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("image/")


# ── Manifest content tests ─────────────────────────────────────────────────────


def test_manifest_name():
    import json
    path = "app/static/manifest.json"
    data = json.loads(open(path).read())
    assert data["name"] == "DecisionDoc AI"
    assert data["short_name"] == "DecisionDoc"


def test_manifest_start_url_and_display():
    import json
    data = json.loads(open("app/static/manifest.json").read())
    assert data["start_url"] == "/"
    assert data["display"] == "standalone"


def test_manifest_icons():
    import json
    data = json.loads(open("app/static/manifest.json").read())
    icons = data.get("icons", [])
    assert len(icons) >= 2
    sizes = {i["sizes"] for i in icons}
    assert "192x192" in sizes
    assert "512x512" in sizes


def test_manifest_shortcuts():
    import json
    data = json.loads(open("app/static/manifest.json").read())
    shortcuts = data.get("shortcuts", [])
    assert len(shortcuts) >= 2
    urls = [s["url"] for s in shortcuts]
    assert any("generate" in u for u in urls)
    assert any("approval" in u for u in urls)


def test_manifest_categories():
    import json
    data = json.loads(open("app/static/manifest.json").read())
    cats = data.get("categories", [])
    assert "productivity" in cats or "business" in cats


# ── sw.js content tests ────────────────────────────────────────────────────────


def test_sw_js_has_install_handler():
    content = open("app/static/sw.js").read()
    assert "addEventListener('install'" in content


def test_sw_js_has_activate_handler():
    content = open("app/static/sw.js").read()
    assert "addEventListener('activate'" in content


def test_sw_js_has_fetch_handler():
    content = open("app/static/sw.js").read()
    assert "addEventListener('fetch'" in content


def test_sw_js_has_push_handler():
    content = open("app/static/sw.js").read()
    assert "addEventListener('push'" in content


def test_sw_js_has_notificationclick_handler():
    content = open("app/static/sw.js").read()
    assert "addEventListener('notificationclick'" in content


def test_sw_js_uses_versioned_cache_name():
    content = open("app/static/sw.js").read()
    assert "decisiondoc-v1.1.17" in content


def test_sw_js_does_not_precache_html_shell():
    content = open("app/static/sw.js").read()
    precache_block = content.split("const PRECACHE_URLS = [", 1)[1].split("];", 1)[0]
    assert "'/'" not in precache_block
    assert "'/static/index.html'" not in precache_block
    assert "HTML_SHELL_PATHS" in content
    assert "networkFirstHtmlStrategy" in content


def test_sw_js_supports_skip_waiting_message():
    content = open("app/static/sw.js").read()
    assert "addEventListener('message'" in content
    assert "SKIP_WAITING" in content


# ── Icon file tests ────────────────────────────────────────────────────────────


def test_icon_192_exists():
    assert os.path.exists("app/static/icons/icon-192.png"), "icon-192.png missing"


def test_icon_512_exists():
    assert os.path.exists("app/static/icons/icon-512.png"), "icon-512.png missing"


def test_icon_192_is_valid_png():
    data = open("app/static/icons/icon-192.png", "rb").read(8)
    # PNG magic bytes: \x89PNG\r\n\x1a\n
    assert data == b"\x89PNG\r\n\x1a\n", "icon-192.png is not a valid PNG"


def test_icon_512_is_valid_png():
    data = open("app/static/icons/icon-512.png", "rb").read(8)
    assert data == b"\x89PNG\r\n\x1a\n", "icon-512.png is not a valid PNG"


# ── generate_icons.py test ─────────────────────────────────────────────────────


def test_generate_icons_runs_without_error(tmp_path, monkeypatch):
    """generate_icons.py should run without raising exceptions."""
    # Run in tmp dir to avoid overwriting production icons
    original_cwd = os.getcwd()
    try:
        os.makedirs(tmp_path / "app/static/icons", exist_ok=True)
        monkeypatch.chdir(tmp_path)
        # Import and run the script
        spec = importlib.util.spec_from_file_location(
            "generate_icons",
            os.path.join(original_cwd, "scripts/generate_icons.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.generate_icons()

        # Verify icons were created
        assert (tmp_path / "app/static/icons/icon-192.png").exists()
        assert (tmp_path / "app/static/icons/icon-512.png").exists()
    finally:
        os.chdir(original_cwd)


# ── index.html PWA meta tags ───────────────────────────────────────────────────


def test_index_html_has_manifest_link():
    content = open("app/static/index.html").read()
    assert 'rel="manifest"' in content
    assert 'href="/manifest.json"' in content


def test_index_html_has_theme_color():
    content = open("app/static/index.html").read()
    assert 'name="theme-color"' in content
    assert "#6366f1" in content


def test_index_html_has_apple_meta():
    content = open("app/static/index.html").read()
    assert "apple-mobile-web-app-capable" in content
    assert "apple-touch-icon" in content


def test_index_html_has_favicon_link():
    content = open("app/static/index.html").read()
    assert 'rel="icon"' in content
    assert 'href="/favicon.ico"' in content


def test_index_html_has_sw_registration():
    content = open("app/static/index.html").read()
    assert "serviceWorker" in content
    assert "register('/sw.js'" in content


def test_index_html_reloads_on_service_worker_update():
    content = open("app/static/index.html").read()
    assert "controllerchange" in content
    assert "SKIP_WAITING" in content
    assert "_swHadControllerAtStartup" in content
    assert "window.location.reload()" in content


def test_index_html_has_install_prompt():
    content = open("app/static/index.html").read()
    assert "beforeinstallprompt" in content
    assert "installPWA" in content


def test_index_html_has_offline_handler():
    content = open("app/static/index.html").read()
    assert "offline-indicator" in content


def test_index_html_has_mobile_bottom_nav():
    content = open("app/static/index.html").read()
    assert "mobile-bottom-nav" in content
    assert "mobile-nav-btn" in content


def test_index_html_stops_notification_polling_on_login_screen():
    content = open("app/static/index.html").read()
    start = content.index("function showLoginScreen()")
    end = content.index("function showRegisterScreen")
    login_screen_block = content[start:end]
    assert "stopNotifPolling();" in login_screen_block
    assert "stopSSE();" in login_screen_block


def test_index_html_restarts_notification_polling_on_visibility_change():
    content = open("app/static/index.html").read()
    assert "document.addEventListener('visibilitychange'" in content
    assert "document.visibilityState === 'hidden'" in content
    assert "if (_sse) {" in content
    assert "startNotifPolling();" in content


def test_index_html_stops_notification_polling_on_logout():
    content = open("app/static/index.html").read()
    start = content.index("function logout()")
    end = content.index("function toggleUserMenu")
    logout_block = content[start:end]
    assert "stopNotifPolling();" in logout_block
    assert "stopSSE();" in logout_block
