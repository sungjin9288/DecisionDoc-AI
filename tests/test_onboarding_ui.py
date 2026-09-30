from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from tests.browser_pages import isolated_page


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "app" / "static" / "index.html"


@pytest.fixture(autouse=True)
def _isolate_static_ui_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")


def _stylesheet_section(html: str, start_marker: str, end_marker: str) -> str:
    start = html.index(start_marker)
    end = html.index(end_marker, start)
    return html[start:end]


def _rule(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]*)\}}", css)
    assert match is not None, f"missing CSS rule for {selector}"
    return re.sub(r"\s+", " ", match.group("body")).strip()


def _onboarding_css(html: str) -> str:
    return _stylesheet_section(
        html,
        "/* ── Onboarding wizard",
        "/* ── G2B deadline badge",
    )


def _stylesheet(html: str) -> str:
    style_start = html.index("<style")
    css_start = html.index(">", style_start) + 1
    css_end = html.index("</style>", css_start)
    return html[css_start:css_end]


def test_onboarding_uses_defined_theme_tokens_and_opaque_readable_surface() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    root = _rule(html, ":root")
    onboarding = _onboarding_css(html)
    modal = _rule(onboarding, ".onboarding-modal")

    defined_tokens = set(re.findall(r"(--[a-z0-9-]+)\s*:", root))
    referenced_tokens = set(re.findall(r"var\((--[a-z0-9-]+)", onboarding))

    assert referenced_tokens <= defined_tokens
    assert "--color-" not in onboarding
    assert "background: var(--surface-solid)" in modal
    assert "color: var(--text)" in modal
    assert re.search(r"--surface-solid:\s*#[0-9a-fA-F]{6}", root)


def test_onboarding_modal_is_bounded_and_scrollable_in_short_viewports() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    onboarding = _onboarding_css(html)
    overlay = _rule(onboarding, "#onboarding-overlay")
    modal = _rule(onboarding, ".onboarding-modal")

    assert "padding: 16px" in overlay
    assert "overflow-y: auto" in overlay
    assert "width: min(100%, 480px)" in modal
    assert "max-height: calc(100dvh - 32px)" in modal
    assert "overflow-y: auto" in modal
    assert "overflow-wrap: anywhere" in modal


def test_onboarding_content_and_actions_wrap_on_mobile() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    onboarding = _onboarding_css(html)
    actions = _rule(onboarding, ".onboarding-actions")
    features = _rule(onboarding, ".onboard-features")
    feature = _rule(onboarding, ".onboard-feature")
    choice = _rule(onboarding, ".onboard-choice")
    style_choice = _rule(onboarding, ".onboard-style-choice")

    assert "flex-wrap: wrap" in actions
    assert "gap: 12px" in actions
    assert "flex-wrap: wrap" in features
    assert "min-width: 0" in feature
    assert "min-width: 0" in choice
    assert "overflow-wrap: anywhere" in choice
    assert "min-width: 0" in style_choice
    assert "overflow-wrap: anywhere" in style_choice
    assert "@media (max-width: 480px)" in onboarding


def test_onboarding_actual_css_renders_opaque_and_inside_viewport(
    tmp_path: Path,
    browser,
) -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    stylesheet = _stylesheet(html)
    screenshot_dir = Path(os.environ.get("ONBOARDING_SCREENSHOT_DIR", tmp_path))
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    modal_markup = """
      <div id="onboarding-overlay">
        <div class="onboarding-modal" role="dialog" aria-modal="true" aria-label="시작 가이드">
          <div class="onboarding-progress">
            <div class="onboarding-dot active"></div>
            <div class="onboarding-dot"></div>
            <div class="onboarding-dot"></div>
            <div class="onboarding-dot"></div>
          </div>
          <div id="onboarding-step-content">
            <h3 class="onboarding-title">DecisionDoc AI에 오신 것을 환영합니다!</h3>
            <div class="onboarding-body">
              <p>입력한 목적에 맞는 전문 문서 생성 흐름을 시작합니다.</p>
              <div class="onboard-features">
                <div class="onboard-feature"><span class="onboard-icon">DOC</span><span>용도별 문서 번들</span></div>
                <div class="onboard-feature"><span class="onboard-icon">G2B</span><span>나라장터 공고 연동</span></div>
                <div class="onboard-feature"><span class="onboard-icon">STYLE</span><span>맞춤 스타일 학습</span></div>
              </div>
            </div>
          </div>
          <div class="onboarding-actions">
            <button type="button" class="btn-outline btn-sm">건너뛰기</button>
            <button type="button" class="btn-primary">다음</button>
          </div>
        </div>
      </div>
    """
    viewports = (
        ("desktop", 1280, 900),
        ("mobile", 390, 844),
        ("short", 390, 360),
    )

    with isolated_page(browser) as page:
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            page.set_content(f"<style>{stylesheet}</style>{modal_markup}")
            rendered = page.locator(".onboarding-modal").evaluate(
                """modal => {
                  const style = getComputedStyle(modal);
                  const rect = modal.getBoundingClientRect();
                  return {
                    backgroundColor: style.backgroundColor,
                    color: style.color,
                    overflowY: style.overflowY,
                    scrollWidth: modal.scrollWidth,
                    clientWidth: modal.clientWidth,
                    rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom },
                    viewport: { width: innerWidth, height: innerHeight },
                  };
                }"""
            )

            assert rendered["backgroundColor"] == "rgb(255, 255, 255)"
            assert rendered["color"] == "rgb(30, 27, 75)"
            assert rendered["overflowY"] == "auto"
            assert rendered["scrollWidth"] <= rendered["clientWidth"]
            assert rendered["rect"]["left"] >= 0
            assert rendered["rect"]["top"] >= 0
            assert rendered["rect"]["right"] <= rendered["viewport"]["width"]
            assert rendered["rect"]["bottom"] <= rendered["viewport"]["height"]

            page.locator(".onboarding-modal").evaluate(
                "modal => { modal.scrollTop = modal.scrollHeight; }"
            )
            actions = page.locator(".onboarding-actions").bounding_box()
            assert actions is not None
            assert actions["y"] >= 0
            assert actions["y"] + actions["height"] <= height

            screenshot_path = screenshot_dir / f"onboarding-{label}.png"
            page.screenshot(path=str(screenshot_path))
            assert screenshot_path.stat().st_size > 0
            print(f"onboarding screenshot: {screenshot_path}")
