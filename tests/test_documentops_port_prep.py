"""Merge prep: port modules stay server-free and the exported type catalog stays current."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from app.bundle_catalog.registry import BUNDLE_REGISTRY
from scripts.export_documentops_type_catalog import DEFAULT_OUTPUT, REPO_ROOT, build_catalog, render

# Modules the port spec copies into the local CLI tool (§2). Procurement decision is
# decoupled during the port itself, so it is not listed here.
PORT_MODULES = [
    "app.services.hwp_service",
    "app.services.excel_service",
    "app.services.local_style_examples",
    "app.services.attachment.core",
    "app.bundle_catalog.registry",
    "app.eval.lints",
    "app.eval.bundle_eval",
]
SERVER_MODULES = ("fastapi", "app.main", "app.providers.base", "app.providers.factory", "app.tenant", "app.auth", "app.storage.state_backend")


@pytest.mark.parametrize("module", PORT_MODULES)
def test_port_module_imports_without_server_or_provider(module: str) -> None:
    probe = (
        "import importlib, json, sys\n"
        f"importlib.import_module({module!r})\n"
        f"print(json.dumps([name for name in {SERVER_MODULES!r} if name in sys.modules]))\n"
    )
    completed = subprocess.run([sys.executable, "-c", probe], cwd=REPO_ROOT, capture_output=True, text=True, check=True)

    assert json.loads(completed.stdout.strip().splitlines()[-1]) == []


def test_tracked_type_catalog_is_current() -> None:
    assert DEFAULT_OUTPUT.read_text(encoding="utf-8") == render(build_catalog())


def test_type_catalog_keeps_every_required_heading_and_drops_few_shots() -> None:
    catalog = build_catalog()
    types = {entry["id"]: entry for entry in catalog["types"]}

    assert sorted(types) == sorted(BUNDLE_REGISTRY)
    for bundle_id, spec in BUNDLE_REGISTRY.items():
        documents = {doc["key"]: doc for doc in types[bundle_id]["documents"]}
        assert list(documents) == spec.doc_keys
        for doc in spec.docs:
            exported = documents[doc.key]
            assert set(exported["required_headings"]) == set(doc.lint_headings) | set(doc.validator_headings)
            assert exported["non_empty_headings"] == doc.critical_non_empty_headings
    rendered = render(catalog)
    for spec in BUNDLE_REGISTRY.values():
        if spec.few_shot_example:
            assert spec.few_shot_example.strip()[:80] not in rendered
