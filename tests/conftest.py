import pytest

from app.config import env_is_enabled


@pytest.fixture(autouse=True)
def _reset_module_store_caches():
    """Clear module-level store caches before every test.

    UserStore and MessageStore use module-level dicts to cache per-tenant
    instances. Without clearing them, a test that registers users could
    pollute subsequent tests that expect an empty store (because pytest's
    tmp_path directories survive until the end of the test session).
    """
    import app.storage.user_store as _us
    import app.storage.message_store as _ms
    import app.storage.style_store as _ss
    import app.storage.notification_store as _ns

    _us._user_stores.clear()
    _ms._msg_stores.clear()
    _ss._style_stores.clear()
    _ns._notification_stores.clear()
    yield
    _us._user_stores.clear()
    _ms._msg_stores.clear()
    _ss._style_stores.clear()
    _ns._notification_stores.clear()


@pytest.fixture
def fake_bold_pdf() -> bytes:
    """A one-page PDF whose heading is drawn six times 0.12 pt apart, as fake bold does, above a plain line."""
    draws = "".join(f"BT /F1 13 Tf {56 + 0.12 * step:.2f} {700 - 0.12 * step:.2f} Td (8. Bid void) Tj ET\n" for step in range(6))
    content = draws + "BT /F1 11 Tf 56 670 Td (void void ....) Tj ET\n"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n{content}endstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Update golden markdown snapshots.",
    )


def pytest_configure(config):
    update_golden = bool(config.getoption("--update-golden"))
    ci_flag = env_is_enabled("CI")
    if update_golden and ci_flag:
        raise pytest.UsageError("--update-golden is not allowed in CI. Update snapshots locally and commit.")
