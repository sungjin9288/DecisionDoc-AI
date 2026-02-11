import os

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Update golden markdown snapshots.",
    )


def pytest_configure(config):
    update_golden = bool(config.getoption("--update-golden"))
    ci_flag = os.getenv("CI", "").strip().lower() in {"1", "true", "yes", "on"}
    if update_golden and ci_flag:
        raise pytest.UsageError("--update-golden is not allowed in CI. Update snapshots locally and commit.")
