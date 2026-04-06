#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

DEFAULT_DATA_DIR = Path("/tmp/decisiondoc-stale-share-demo")
DEFAULT_MANIFEST_NAME = "procurement-stale-share-demo.json"


@dataclass
class DemoUIPlaytestResult:
    bundle_id: str
    project_id: str
    share_id: str
    focused_review_url: str
    public_share_url: str
    focused_review_screenshot: str
    public_share_screenshot: str


def _resolve_manifest_path(*, data_dir: Path, manifest_path: str = "") -> Path:
    candidate = Path(str(manifest_path).strip()).expanduser() if str(manifest_path).strip() else data_dir / DEFAULT_MANIFEST_NAME
    return candidate


def _load_manifest(*, data_dir: Path, manifest_path: str = "") -> dict[str, Any]:
    resolved = _resolve_manifest_path(data_dir=data_dir, manifest_path=manifest_path)
    if not resolved.exists():
        raise SystemExit(f"Demo manifest not found: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Failed to read demo manifest {resolved}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Demo manifest must be a JSON object: {resolved}")
    return payload


def _build_output_dir(output_dir: str = "") -> Path:
    target = Path(str(output_dir).strip()).expanduser() if str(output_dir).strip() else REPO_ROOT / "output" / "playwright" / "procurement-stale-share-demo"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _bundle_label(bundle_id: str) -> str:
    if bundle_id == "proposal_kr":
        return "제안서"
    if bundle_id == "bid_decision_kr":
        return "의사결정 문서"
    return bundle_id


def _expect_text_contains(page, selector: str, expected: str, *, timeout_ms: int = 15000) -> None:
    page.wait_for_selector(selector, timeout=timeout_ms)
    text = page.locator(selector).inner_text()
    if expected not in text:
        raise SystemExit(f"{selector} did not contain {expected!r}: {text!r}")


def _wait_for_first_visible_selector(page, selectors: list[str], *, timeout_ms: int = 15000) -> str:
    deadline = time.monotonic() + (max(timeout_ms, 1) / 1000.0)
    while True:
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            break
        per_selector_timeout = max(250, min(750, remaining_ms))
        for selector in selectors:
            try:
                page.wait_for_selector(selector, state="visible", timeout=per_selector_timeout)
                return selector
            except PlaywrightTimeoutError:
                continue
    joined = ", ".join(selectors)
    raise PlaywrightTimeoutError(f"Timed out waiting for any selector to become visible: {joined}")


def _ensure_demo_home_ready(page, *, username: str, password: str) -> None:
    ready_selector = _wait_for_first_visible_selector(
        page,
        [".bundle-card", "#login-screen"],
        timeout_ms=15000,
    )
    if ready_selector != "#login-screen":
        return
    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.evaluate("document.getElementById('login-form')?.requestSubmit()")
    page.wait_for_selector(".bundle-card", state="visible", timeout=15000)
    _dismiss_onboarding_if_present(page)


def _dismiss_onboarding_if_present(page) -> None:
    page.evaluate(
        """
        (() => {
          try {
            localStorage.setItem('onboarding_done', '1');
          } catch (error) {
            // ignore storage failures in the demo helper
          }
          if (typeof window.finishOnboarding === 'function') {
            window.finishOnboarding();
          }
          const overlay = document.getElementById('onboarding-overlay');
          if (overlay) overlay.remove();
          return true;
        })()
        """
    )


def _restore_stale_share_focus_from_url(
    page,
    *,
    focused_review_url: str,
    username: str,
    password: str,
) -> None:
    page.goto(focused_review_url)
    ready_selector = _wait_for_first_visible_selector(
        page,
        [".bundle-card", "#login-screen"],
        timeout_ms=15000,
    )
    if ready_selector == "#login-screen":
        page.fill("#login-username", username)
        page.fill("#login-password", password)
        page.evaluate("document.getElementById('login-form')?.requestSubmit()")
        page.wait_for_selector(".bundle-card", state="visible", timeout=15000)
        page.goto(focused_review_url)
        page.wait_for_selector(".bundle-card", state="visible", timeout=15000)
    _dismiss_onboarding_if_present(page)
    page.evaluate(
        """
        (async () => {
          if (typeof window.restoreLocationProcurementSummaryFromUrl === 'function') {
            return await window.restoreLocationProcurementSummaryFromUrl();
          }
          return false;
        })()
        """
    )


def _open_stale_share_focus_from_locations(page, *, tenant_id: str, project_id: str, base_url: str, username: str, password: str) -> None:
    page.goto(base_url)
    _ensure_demo_home_ready(page, username=username, password=password)
    page.evaluate(
        f"window.openLocationProcurementFocusedStaleShareReview({json.dumps(tenant_id)}, {json.dumps(project_id)})"
    )


def _force_location_procurement_modal_visible(page) -> None:
    page.evaluate(
        """
        (() => {
          const modal = document.getElementById('location-procurement-modal');
          if (!modal) return false;
          modal.style.display = 'flex';
          if (typeof renderLocationProcurementSummaryModalFromState === 'function') {
            renderLocationProcurementSummaryModalFromState();
          }
          return true;
        })()
        """
    )


def _ensure_stale_share_modal_visible(page, *, tenant_id: str, project_id: str, base_url: str, username: str, password: str) -> None:
    try:
        page.wait_for_selector("#location-procurement-modal", state="visible", timeout=5000)
        return
    except PlaywrightTimeoutError:
        pass

    try:
        _restore_stale_share_focus_from_url(
            page,
            focused_review_url=build_focused_review_url(base_url, tenant_id, project_id),
            username=username,
            password=password,
        )
        page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
        return
    except PlaywrightTimeoutError:
        pass

    button_selector = (
        f'[data-location-procurement-stale-share-focus-review="{tenant_id}"]'
        f'[data-location-procurement-project="{project_id}"]'
    )
    try:
        page.wait_for_selector(button_selector, state="visible", timeout=5000)
        page.locator(button_selector).first.click()
        page.wait_for_selector("#location-procurement-modal", state="visible", timeout=15000)
        return
    except PlaywrightTimeoutError:
        pass

    page.evaluate(
        f"window.openLocationProcurementFocusedStaleShareReview({json.dumps(tenant_id)}, {json.dumps(project_id)})"
    )
    try:
        page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
        return
    except PlaywrightTimeoutError:
        try:
            _force_location_procurement_modal_visible(page)
            page.wait_for_selector("#location-procurement-modal", state="visible", timeout=5000)
            return
        except PlaywrightTimeoutError:
            _open_stale_share_focus_from_locations(
                page,
                tenant_id=tenant_id,
                project_id=project_id,
                base_url=base_url,
                username=username,
                password=password,
            )
        try:
            page.wait_for_selector("#location-procurement-modal", state="visible", timeout=15000)
            return
        except PlaywrightTimeoutError:
            _force_location_procurement_modal_visible(page)
            page.wait_for_selector("#location-procurement-modal", state="visible", timeout=5000)


def build_focused_review_url(base_url: str, tenant_id: str, project_id: str) -> str:
    return (
        f"{base_url}/?location_procurement_tenant={tenant_id}"
        f"&location_procurement_activity_actions=share.create"
        f"&location_procurement_focus_project={project_id}"
    )


def playtest_procurement_stale_share_demo(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    manifest_path: str = "",
    base_url: str = "",
    headed: bool = False,
    slow_mo_ms: int = 0,
    output_dir: str = "",
    playwright_factory: Callable[[], Any] = sync_playwright,
) -> DemoUIPlaytestResult:
    manifest = _load_manifest(data_dir=Path(data_dir), manifest_path=manifest_path)
    seed = manifest.get("seed") if isinstance(manifest.get("seed"), dict) else {}
    verification = manifest.get("verification") if isinstance(manifest.get("verification"), dict) else {}
    resolved_base_url = str(base_url).strip() or str(manifest.get("base_url", "")).strip()
    if not resolved_base_url:
        raise SystemExit("Demo manifest does not contain base_url and none was provided.")

    username = str(seed.get("username", "")).strip()
    password = str(seed.get("password", ""))
    project_id = str(seed.get("project_id", "")).strip() or str(verification.get("project_id", "")).strip()
    share_id = str(seed.get("share_id", "")).strip() or str(verification.get("share_id", "")).strip()
    tenant_id = str(verification.get("tenant_id", "")).strip() or "system"
    bundle_id = str(verification.get("bundle_id", "")).strip() or str(seed.get("shared_bundle_id", "")).strip() or "proposal_kr"
    bundle_label = _bundle_label(bundle_id)
    focused_review_url = str(verification.get("internal_focused_review_url", "")).strip() or str(seed.get("internal_focused_review_url", "")).strip()
    public_share_url = str(verification.get("public_share_url", "")).strip() or str(seed.get("public_share_url", "")).strip()
    stale_status_copy = str(verification.get("stale_status_copy", "")).strip() or "현재 procurement 대비 이전 council 기준"
    if not username or not password or not focused_review_url or not public_share_url or not project_id or not share_id:
        raise SystemExit("Demo manifest is missing required seed/verification fields.")

    screenshots_dir = _build_output_dir(output_dir)
    focused_review_screenshot = screenshots_dir / "focused-review.png"
    public_share_screenshot = screenshots_dir / "public-share.png"

    with playwright_factory() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=int(slow_mo_ms or 0))
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(resolved_base_url)
            page.wait_for_selector("#login-screen", timeout=15000)
            page.fill("#login-username", username)
            page.fill("#login-password", password)
            page.evaluate("document.getElementById('login-form')?.requestSubmit()")
            page.wait_for_selector(".bundle-card", timeout=15000)

            _ensure_stale_share_modal_visible(
                page,
                tenant_id=tenant_id,
                project_id=project_id,
                base_url=resolved_base_url,
                username=username,
                password=password,
            )
            page.wait_for_selector(".location-procurement-focus", state="visible", timeout=15000)
            _expect_text_contains(page, ".location-procurement-focus", bundle_label)
            _expect_text_contains(page, ".location-procurement-focus", stale_status_copy)
            page.screenshot(path=str(focused_review_screenshot), full_page=True)

            _dismiss_onboarding_if_present(page)
            page.locator('.location-procurement-focus [data-location-procurement-open]').first.click(force=True)
            page.wait_for_selector(".decision-council-panel", state="visible", timeout=15000)
            _expect_text_contains(page, ".decision-council-panel", "Decision Council v1")
            _expect_text_contains(page, ".decision-council-panel", "bid_decision_kr")
            _expect_text_contains(page, ".decision-council-panel", "proposal_kr")
            if not page.locator(f'[data-decision-council-generate-proposal="{project_id}"]').is_disabled():
                raise SystemExit("Expected stale proposal council generate CTA to stay disabled in the demo.")

            page.goto(public_share_url)
            page.wait_for_selector('[data-shared-decision-council-warning="stale_procurement"]', timeout=15000)
            _expect_text_contains(page, '[data-shared-decision-council-warning="stale_procurement"]', stale_status_copy)
            page.screenshot(path=str(public_share_screenshot), full_page=True)
        finally:
            context.close()
            browser.close()

    return DemoUIPlaytestResult(
        bundle_id=bundle_id,
        project_id=project_id,
        share_id=share_id,
        focused_review_url=focused_review_url,
        public_share_url=public_share_url,
        focused_review_screenshot=str(focused_review_screenshot),
        public_share_screenshot=str(public_share_screenshot),
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a browser playtest against the seeded procurement stale-share demo manifest.",
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--manifest", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--slow-mo-ms", type=int, default=0)
    return parser.parse_args(argv)


def _print_result(result: DemoUIPlaytestResult) -> None:
    print("Playtested procurement stale-share demo UI.")
    print("")
    print(f"bundle_id: {result.bundle_id}")
    print(f"project_id: {result.project_id}")
    print(f"share_id: {result.share_id}")
    print("")
    print("Screenshots")
    print(f"  focused review: {result.focused_review_screenshot}")
    print(f"  public share: {result.public_share_screenshot}")
    print("")
    print("Visited URLs")
    print(f"  focused review: {result.focused_review_url}")
    print(f"  public share: {result.public_share_url}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    result = playtest_procurement_stale_share_demo(
        data_dir=Path(str(args.data_dir)).expanduser(),
        manifest_path=str(args.manifest).strip(),
        base_url=str(args.base_url).strip(),
        headed=bool(args.headed),
        slow_mo_ms=int(args.slow_mo_ms),
        output_dir=str(args.output_dir).strip(),
    )
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
