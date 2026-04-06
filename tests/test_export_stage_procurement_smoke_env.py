from __future__ import annotations

from pathlib import Path

from scripts import export_stage_procurement_smoke_env as exporter


def _write_env_file(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "DECISIONDOC_API_KEY=repo-api-key",
                "DECISIONDOC_OPS_KEY=repo-ops-key",
                "G2B_API_KEY_DEV=dev-g2b-key",
                "PROCUREMENT_SMOKE_URL_OR_NUMBER_DEV=20260405001-00",
                "PROCUREMENT_SMOKE_TENANT_ID_DEV=tenant-dev",
                "PROCUREMENT_SMOKE_USERNAME_DEV=dev-user",
                "PROCUREMENT_SMOKE_PASSWORD_DEV=dev-pass",
                "G2B_API_KEY_PROD=prod-g2b-key",
                "PROCUREMENT_SMOKE_URL_OR_NUMBER_PROD=20260407001-00",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_export_stage_procurement_smoke_env_writes_expected_mapping(tmp_path: Path) -> None:
    input_env = tmp_path / "github-actions.env"
    output_env = tmp_path / "stage-proc.env"
    _write_env_file(input_env)

    path = exporter.export_stage_procurement_smoke_env(
        stage="dev",
        input_env_file=input_env,
        output_env_file=output_env,
        base_url="https://stage.example.com/",
        provider="mock",
        timeout_sec="45",
    )

    assert path == output_env
    contents = output_env.read_text(encoding="utf-8")
    assert "SMOKE_BASE_URL=https://stage.example.com" in contents
    assert "SMOKE_API_KEY=repo-api-key" in contents
    assert "SMOKE_OPS_KEY=repo-ops-key" in contents
    assert "G2B_API_KEY=dev-g2b-key" in contents
    assert "SMOKE_PROCUREMENT_URL_OR_NUMBER=20260405001-00" in contents
    assert "SMOKE_TENANT_ID=tenant-dev" in contents
    assert "PROCUREMENT_SMOKE_USERNAME=dev-user" in contents
    assert "PROCUREMENT_SMOKE_PASSWORD=dev-pass" in contents
    assert "SMOKE_PROVIDER=mock" in contents
    assert "SMOKE_TIMEOUT_SEC=45" in contents


def test_export_stage_procurement_smoke_env_requires_stage_specific_values(tmp_path: Path) -> None:
    input_env = tmp_path / "github-actions.env"
    output_env = tmp_path / "stage-proc.env"
    input_env.write_text("DECISIONDOC_API_KEY=repo-api-key\n", encoding="utf-8")

    try:
        exporter.export_stage_procurement_smoke_env(
            stage="dev",
            input_env_file=input_env,
            output_env_file=output_env,
            base_url="https://stage.example.com",
        )
    except SystemExit as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected SystemExit for missing stage smoke values")

    assert "G2B_API_KEY_DEV" in message


def test_main_uses_cli_and_defaults(tmp_path: Path, monkeypatch) -> None:
    input_env = tmp_path / "github-actions.env"
    output_env = tmp_path / "stage-proc.env"
    _write_env_file(input_env)
    monkeypatch.setenv("SMOKE_PROVIDER", "gemini")
    monkeypatch.setenv("SMOKE_TIMEOUT_SEC", "55")

    result = exporter.main(
        [
            "--stage",
            "prod",
            "--env-file",
            str(input_env),
            "--output",
            str(output_env),
            "--base-url",
            "https://prod.example.com",
        ]
    )

    assert result == 0
    contents = output_env.read_text(encoding="utf-8")
    assert "SMOKE_BASE_URL=https://prod.example.com" in contents
    assert "SMOKE_API_KEY=repo-api-key" in contents
    assert "G2B_API_KEY=prod-g2b-key" in contents
    assert "SMOKE_PROCUREMENT_URL_OR_NUMBER=20260407001-00" in contents
    assert "SMOKE_PROVIDER=gemini" in contents
    assert "SMOKE_TIMEOUT_SEC=55" in contents


def test_main_uses_process_argv_when_not_explicitly_provided(tmp_path: Path, monkeypatch) -> None:
    input_env = tmp_path / "github-actions.env"
    output_env = tmp_path / "stage-proc.env"
    _write_env_file(input_env)
    monkeypatch.setattr(
        exporter.sys,
        "argv",
        [
            "export_stage_procurement_smoke_env.py",
            "--stage",
            "dev",
            "--env-file",
            str(input_env),
            "--output",
            str(output_env),
            "--base-url",
            "https://dev.example.com",
        ],
    )

    result = exporter.main()

    assert result == 0
    contents = output_env.read_text(encoding="utf-8")
    assert "SMOKE_BASE_URL=https://dev.example.com" in contents
