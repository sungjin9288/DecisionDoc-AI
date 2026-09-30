"""Pages for static UI tests on pytest-playwright's shared browser.

pytest-playwright keeps one sync Playwright session open for the whole run, so a
second ``sync_playwright()`` in the same process fails once a browser test has
started it. Each page gets its own context to keep tests isolated.
"""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def isolated_page(browser, **context_args):
    context = browser.new_context(**context_args)
    try:
        yield context.new_page()
    finally:
        context.close()
