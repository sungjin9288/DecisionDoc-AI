from __future__ import annotations

import json
from pathlib import Path

from app.services.procurement_decision_package_service import (
    AUDIT_MANIFEST_NAME,
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    CLI_CONTRACT_MANIFEST_CONTRACT_VERSION,
    CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FIELDS,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_RESULT_NAME,
    CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS,
    CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME,
    DECISION_PACKAGE_NAME,
    EXPORT_MANIFEST_NAME,
    LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH,
    PENDING_SIGNOFF_NAME,
    PROPOSAL_HANDOFF_NAME,
    REVIEWER_HANDOFF_NAME,
    SIGNOFF_SUMMARY_NAME,
    check_cli_contract_manifest_validation_result,
    validate_cli_contract_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH
SAMPLE_DIR = MANIFEST_PATH.parent
SAMPLE_README_PATH = SAMPLE_DIR / "README.md"
EXPECTED_CLI_CONTRACT_COUNT = len(CLI_CONTRACT_MANIFEST_CASE_SCRIPTS)
SAMPLE_README_FILES_HEADING = "## Files"
SAMPLE_README_NEXT_HEADING = "## Intended Use"
SAMPLE_README_BOUNDARY_HEADING = "## Boundary"
SAMPLE_README_FILE_ORDER = [
    "sample_input.json",
    "expected_decision_package.json",
    "cli_contract_manifest.json",
    "cli_contract_manifest_validation_result.json",
    "cli_contract_manifest_validation_check_result.json",
]
SAMPLE_README_LOCAL_EVIDENCE_COMMANDS = [
    (
        "python3 scripts/build_procurement_decision_package_sample.py "
        "--out-dir /tmp/decisiondoc-procurement-demo"
    ),
    "python3 scripts/validate_procurement_decision_package_sample.py",
    (
        "python3 scripts/validate_procurement_decision_package_cli_contract_manifest.py "
        "--write-result"
    ),
    (
        "python3 scripts/check_procurement_decision_package_cli_contract_manifest_result.py "
        "--write-result"
    ),
]
SAMPLE_README_FOCUSED_REGRESSION_TESTS = [
    "tests/test_procurement_decision_package_sample.py",
    "tests/test_procurement_decision_package_builder.py",
    "tests/test_procurement_decision_package_review_workspace.py",
    "tests/test_procurement_decision_package_cli_contract_manifest.py",
    "tests/test_check_procurement_decision_package_cli_contract_manifest_result.py",
    "tests/test_procurement_decision_package_docs_contract.py",
    "tests/test_procurement_decision_package_cli_failure_contract.py",
    "tests/test_procurement_decision_package_cli_success_contract.py",
]
CONTRACT_DOCS = [
    "README.md",
    "docs/README.md",
    "docs/specs/public_procurement_copilot/STATUS.md",
    "docs/roadmap.md",
    "docs/product_direction.md",
    "docs/product_execution_plan.md",
    "docs/product_local_demo_runbook.md",
    "docs/product_demo_scenario.md",
    "docs/case-study.md",
    "docs/project-card.md",
    "docs/interview-story.md",
    "docs/resume-bullets.md",
    "docs/evidence-checklist.md",
    "docs/evidence-gallery.md",
    "docs/implementation-evidence.md",
    "docs/readme-improvement.md",
    "docs/samples/procurement_decision_package_local_demo/README.md",
]
REQUIRED_MARKERS = [
    LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH.name,
    Path(CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["cli_contract_manifest_validator"]).name,
    Path(CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["cli_contract_manifest_result_checker"]).name,
    "contract_version",
    "--write-result",
    "--result-path",
]
FIELD_CONTRACT_DOCS = [
    "docs/product_local_demo_runbook.md",
    "docs/product_demo_scenario.md",
    "docs/samples/procurement_decision_package_local_demo/README.md",
]
FIELD_CONTRACT_MARKERS = [
    "success_required_fields_by_case",
    "failure_required_fields_by_case",
    "cli_contract_fingerprint",
    "stdout_json_contract",
    "cli_contracts[]",
    "stdout field order",
    "manifest field order",
    "stdout_json_contract field order",
    "cli_contracts[] field order",
    "validation result field order",
    "check result field order",
    "case-map order",
    DECISION_PACKAGE_NAME,
    "central review artifact",
    "operator-readable validation summary",
    "operator_summary",
    "next_review_action",
    "validation_summary field order",
    REVIEWER_HANDOFF_NAME,
    "reviewer handoff metadata",
    PROPOSAL_HANDOFF_NAME,
    "package-to-proposal handoff metadata",
    PENDING_SIGNOFF_NAME,
    "pending review record",
    SIGNOFF_SUMMARY_NAME,
    "reviewer-readable sign-off summary",
    AUDIT_MANIFEST_NAME,
    "audit packet index",
    EXPORT_MANIFEST_NAME,
    "fixed field order",
]
LOCAL_MACHINE_PATH_FRAGMENTS = [
    "/Users/",
    "/sungjin/",
    "/DecisionDoc-AI/",
]
PLACEHOLDER_PURPOSES = {"", "tbd", "todo", "n/a"}
SAMPLE_RECEIPT_FIELD_ORDER = {
    CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME: (
        CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS
    ),
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_RESULT_NAME: (
        CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FIELDS
    ),
}
SAMPLE_CHECK_RECEIPT_OWN_FIELDS = {
    "check",
    "validation_result_path",
    "validation_result_checked",
}
SAMPLE_VALIDATION_RESULT_PATH = (
    LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH.parent
    / CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME
)
SAMPLE_RECEIPT_PATH_FIELDS = {
    CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME: {
        "manifest_path": str(LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH),
    },
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_RESULT_NAME: {
        "manifest_path": str(LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH),
        "validation_result_path": str(SAMPLE_VALIDATION_RESULT_PATH),
    },
}


def _load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_sample_json(file_name: str) -> dict[str, object]:
    return json.loads((SAMPLE_DIR / file_name).read_text(encoding="utf-8"))


def _read_doc(doc_name: str) -> str:
    return (ROOT / doc_name).read_text(encoding="utf-8")


def _assert_docs_contain_markers(doc_names: list[str], markers: list[str]) -> None:
    for doc_name in doc_names:
        text = _read_doc(doc_name)
        for marker in markers:
            assert marker in text, f"{doc_name} missing {marker}"


def _current_sample_artifact_names() -> list[str]:
    return sorted(
        sample_path.name
        for sample_path in SAMPLE_DIR.iterdir()
        if sample_path.is_file() and sample_path.name != SAMPLE_README_PATH.name
    )


def _sample_readme_section(
    start_heading: str,
    *,
    end_heading: str | None = None,
) -> str:
    readme_text = SAMPLE_README_PATH.read_text(encoding="utf-8")
    _, heading, section = readme_text.partition(start_heading)
    assert heading, f"README missing {start_heading}"

    if end_heading is None:
        return section

    section, heading, _ = section.partition(end_heading)
    assert heading, f"README missing {end_heading}"
    return section


def _sample_readme_files_section() -> str:
    return _sample_readme_section(
        SAMPLE_README_FILES_HEADING,
        end_heading=SAMPLE_README_NEXT_HEADING,
    )


def _sample_readme_file_table_rows() -> list[tuple[str, str]]:
    files_section = _sample_readme_files_section()
    rows = []

    for line in files_section.splitlines():
        if not line.startswith("| `"):
            continue

        _, file_name, purpose, *_ = line.split("|")
        rows.append((file_name.strip().strip("`"), purpose.strip()))

    return rows


def _sample_readme_bash_commands() -> list[str]:
    readme_text = SAMPLE_README_PATH.read_text(encoding="utf-8")
    commands = []
    in_bash_block = False
    bash_block_count = 0

    for line in readme_text.splitlines():
        if line == "```bash":
            bash_block_count += 1
            in_bash_block = True
            continue
        if in_bash_block and line == "```":
            in_bash_block = False
            continue
        if in_bash_block and line:
            commands.append(line)

    assert bash_block_count > 0, "README missing bash command block"
    assert not in_bash_block, "README has an unclosed bash command block"
    return commands


def _sample_readme_focused_regression_command() -> str:
    return "pytest -q " + " ".join(SAMPLE_README_FOCUSED_REGRESSION_TESTS)


def _expected_sample_readme_bash_commands() -> list[str]:
    return [
        *SAMPLE_README_LOCAL_EVIDENCE_COMMANDS,
        _sample_readme_focused_regression_command(),
    ]


def _sample_readme_boundary_items() -> list[str]:
    boundary_section = _sample_readme_section(SAMPLE_README_BOUNDARY_HEADING)
    boundary_items = []

    for line in boundary_section.splitlines():
        line = line.strip()
        if line.startswith("- "):
            boundary_items.append(line[2:].rstrip(",."))

    return boundary_items


def _readable_external_action(action: object) -> str:
    word_overrides = {
        "api": "API",
        "aws": "AWS",
    }

    return " ".join(
        word_overrides.get(word, word)
        for word in str(action).split("_")
    )


def _validate_current_manifest(manifest_path: Path) -> dict[str, object]:
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path

    return validate_cli_contract_manifest(manifest_path, repo_root=ROOT)


def test_procurement_decision_package_docs_reference_versioned_cli_contract() -> None:
    manifest = _load_manifest()
    assert manifest["schema_purpose"] == CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE
    assert manifest["contract_version"] == CLI_CONTRACT_MANIFEST_CONTRACT_VERSION
    assert len(manifest["cli_contracts"]) == EXPECTED_CLI_CONTRACT_COUNT

    _assert_docs_contain_markers(CONTRACT_DOCS, REQUIRED_MARKERS)
    _assert_docs_contain_markers(FIELD_CONTRACT_DOCS, FIELD_CONTRACT_MARKERS)


def test_procurement_decision_package_sample_artifacts_are_portable() -> None:
    for sample_path in sorted(SAMPLE_DIR.iterdir()):
        if not sample_path.is_file():
            continue

        sample_text = sample_path.read_text(encoding="utf-8")
        for path_fragment in LOCAL_MACHINE_PATH_FRAGMENTS:
            assert (
                path_fragment not in sample_text
            ), f"{sample_path.name} embeds {path_fragment}"


def test_procurement_decision_package_sample_readme_lists_current_artifacts() -> None:
    sample_readme_rows = _sample_readme_file_table_rows()
    sample_readme_names = [name for name, _ in sample_readme_rows]

    assert sorted(SAMPLE_README_FILE_ORDER) == _current_sample_artifact_names()
    assert sample_readme_names == SAMPLE_README_FILE_ORDER

    for artifact_name, purpose in sample_readme_rows:
        assert purpose.lower() not in PLACEHOLDER_PURPOSES, artifact_name


def test_procurement_decision_package_sample_readme_keeps_command_sequence() -> None:
    assert _sample_readme_bash_commands() == _expected_sample_readme_bash_commands()


def test_procurement_decision_package_sample_readme_boundary_matches_manifest() -> None:
    manifest = _load_manifest()
    expected_boundary_items = [
        _readable_external_action(action)
        for action in manifest["external_actions_excluded"]
    ]

    assert _sample_readme_boundary_items() == expected_boundary_items


def test_procurement_decision_package_sample_receipts_keep_field_order() -> None:
    for receipt_name, expected_fields in SAMPLE_RECEIPT_FIELD_ORDER.items():
        assert list(_load_sample_json(receipt_name)) == list(expected_fields)


def test_procurement_decision_package_sample_receipts_are_passed_results() -> None:
    validation_result = _load_sample_json(CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME)
    check_result = _load_sample_json(CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_RESULT_NAME)

    assert validation_result["status"] == "passed"
    assert check_result["status"] == "passed"
    assert check_result["check"] == CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME
    assert check_result["validation_result_checked"] is True


def test_procurement_decision_package_sample_receipts_use_expected_paths() -> None:
    for receipt_name, expected_paths in SAMPLE_RECEIPT_PATH_FIELDS.items():
        receipt = _load_sample_json(receipt_name)
        for field_name, expected_path in expected_paths.items():
            assert receipt[field_name] == expected_path


def test_procurement_decision_package_sample_check_receipt_mirrors_validation() -> None:
    validation_result = _load_sample_json(CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME)
    check_result = _load_sample_json(CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_RESULT_NAME)

    mirrored_fields = [
        field_name
        for field_name in check_result
        if field_name in validation_result
        and field_name not in SAMPLE_CHECK_RECEIPT_OWN_FIELDS
    ]

    assert mirrored_fields
    for field_name in mirrored_fields:
        assert check_result[field_name] == validation_result[field_name], field_name


def test_procurement_decision_package_sample_validation_receipt_matches_current_manifest() -> None:
    assert _load_sample_json(
        CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME
    ) == _validate_current_manifest(LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH)


def test_procurement_decision_package_sample_check_receipt_matches_current_manifest() -> None:
    check_result = check_cli_contract_manifest_validation_result(
        SAMPLE_DIR / CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME,
        expected_schema_purpose=CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
        validate_current_manifest=_validate_current_manifest,
        display_base_dir=ROOT,
    )

    assert check_result == _load_sample_json(
        CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_RESULT_NAME
    )
