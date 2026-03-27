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
