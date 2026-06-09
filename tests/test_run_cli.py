from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import TypeAdapter
from typer.testing import CliRunner

from signal2ship.cli import app
from signal2ship.models import (
    DeploymentReadinessBundle,
    GeneratedAppCommand,
    GeneratedAppContract,
    PolicyReadinessReview,
    Signal2ShipRunManifest,
    Signal2ShipWorkflowResult,
    StorePack,
    VerificationRecord,
)
from tests.fixtures import make_last30days_markdown

if TYPE_CHECKING:
    import pytest

    from signal2ship.llm import OpenRouterModelTier


@dataclass(frozen=True, slots=True)
class StaticLLMClient:
    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_tier: OpenRouterModelTier = "flash",
    ) -> str:
        _ = (system_prompt, user_prompt, model_tier)
        return "Configured LLM guidance grounded in the supplied research artifact."


def test_run_cli_prints_local_runtime_manifest() -> None:
    # Given
    runner = CliRunner()

    # When
    result = runner.invoke(app, ["run", "AI coding agent workflow pain"])

    # Then
    assert result.exit_code == 0
    manifest = Signal2ShipRunManifest.model_validate_json(result.output)
    assert manifest.runtime.mode == "local_codex_desktop"
    assert manifest.deploy_target.name == "oci_preview_optional"


def test_run_cli_stops_at_spec_approval_from_raw_research(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    runner = CliRunner()
    raw_file = tmp_path / "last30days.md"
    output_dir = tmp_path / "outputs"
    app_dir = tmp_path / "apps" / "generated"
    expected_slug = "recurring-agent-workflows-are-hard-to-control"
    expected_artifacts = [
        output_dir / "signals" / "evidence_ledger.json",
        output_dir / "ideas" / "opportunity_scores.json",
        output_dir / "ideas" / "scored_ideas.md",
        output_dir / "product" / "MVP_SPEC.md",
        output_dir / "product" / "IDEA_SPEC_APPROVAL.json",
        output_dir / "product" / "IDEA_SPEC_APPROVAL.md",
    ]
    _ = raw_file.write_text(make_last30days_markdown(), encoding="utf-8")
    monkeypatch.setattr(
        "signal2ship.cli.build_openrouter_client",
        _build_static_llm_client,
    )

    # When
    result = runner.invoke(
        app,
        [
            "run",
            "AI coding agent workflow pain",
            "--raw-file",
            str(raw_file),
            "--output-dir",
            str(output_dir),
            "--app-dir",
            str(app_dir),
        ],
    )

    # Then
    assert result.exit_code == 0, result.output
    run_result = Signal2ShipWorkflowResult.model_validate_json(result.output)
    assert run_result.status == "needs_spec_approval"
    assert run_result.selected_opportunity == expected_slug
    assert run_result.artifacts == [str(artifact) for artifact in expected_artifacts]
    assert run_result.app_dir is None
    assert run_result.run_id is not None
    assert run_result.run_state == "needs_spec_approval"
    assert run_result.approval_packet == str(
        output_dir / "product" / "IDEA_SPEC_APPROVAL.json",
    )
    for artifact in expected_artifacts:
        assert artifact.is_file(), f"missing artifact: {artifact}"
    assert "AI coding agent workflow pain" in (
        output_dir / "product" / "MVP_SPEC.md"
    ).read_text(encoding="utf-8")
    approval_packet = (output_dir / "product" / "IDEA_SPEC_APPROVAL.md").read_text(
        encoding="utf-8",
    )
    assert "Target user:" in approval_packet
    assert "## MVP Scope" in approval_packet
    assert "## Policy / Privacy Notes" in approval_packet
    assert "App creation is blocked" in approval_packet
    assert not app_dir.exists()
    assert not (
        output_dir / "launch" / "OCI_PREVIEW_BUNDLE.md"
    ).exists()
    assert not (
        output_dir / "reviews" / "QA_REVIEW.md"
    ).exists()


def test_approve_spec_then_build_approved_generates_app_contract(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    runner = CliRunner()
    raw_file = tmp_path / "last30days.md"
    output_dir = tmp_path / "outputs"
    app_dir = tmp_path / "apps" / "generated"
    approval_path = tmp_path / "outputs" / "product" / "SPEC_APPROVAL.json"
    expected_slug = "recurring-agent-workflows-are-hard-to-control"
    _ = raw_file.write_text(make_last30days_markdown(), encoding="utf-8")
    monkeypatch.setattr(
        "signal2ship.cli.build_openrouter_client",
        _build_static_llm_client,
    )
    _ = runner.invoke(
        app,
        [
            "run",
            "AI coding agent workflow pain",
            "--raw-file",
            str(raw_file),
            "--output-dir",
            str(output_dir),
            "--app-dir",
            str(app_dir),
        ],
    )

    # When
    approve_result = runner.invoke(
        app,
        [
            "approve-spec",
            str(output_dir / "product" / "IDEA_SPEC_APPROVAL.json"),
            "--output",
            str(approval_path),
            "--operator",
            "hjongc",
            "--reason",
            "Approved test MVP scope.",
            "--approved-at",
            "2026-06-09T10:00:00+09:00",
        ],
    )
    build_result = runner.invoke(
        app,
        [
            "build-approved",
            str(approval_path),
            "--output-dir",
            str(output_dir),
            "--app-dir",
            str(app_dir),
        ],
    )
    verify_result = runner.invoke(
        app,
        [
            "verify-app",
            str((app_dir / expected_slug) / "APP_CONTRACT.json"),
            "--output-dir",
            str(output_dir),
        ],
    )
    verification_record_path = output_dir / "reviews" / "VERIFICATION_RECORD.json"
    bundle_result = runner.invoke(
        app,
        [
            "prepare-deploy-bundle",
            str((app_dir / expected_slug) / "APP_CONTRACT.json"),
            str(verification_record_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    store_pack_result = runner.invoke(
        app,
        [
            "generate-store-pack",
            str((app_dir / expected_slug) / "APP_CONTRACT.json"),
            str(verification_record_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    # Then
    assert approve_result.exit_code == 0, approve_result.output
    assert build_result.exit_code == 0, build_result.output
    assert verify_result.exit_code == 0, verify_result.output
    assert bundle_result.exit_code == 0, bundle_result.output
    assert store_pack_result.exit_code == 0, store_pack_result.output
    workflow = Signal2ShipWorkflowResult.model_validate_json(build_result.output)
    app_root = app_dir / expected_slug
    contract_path = app_root / "APP_CONTRACT.json"
    manifest_path = app_root / "command-manifest.json"
    assert workflow.status == "app_generated"
    assert workflow.run_state == "creating_app"
    assert workflow.app_dir == str(app_root)
    assert workflow.app_contract == str(contract_path)
    assert contract_path.is_file()
    assert manifest_path.is_file()
    assert (app_root / "package.json").is_file()
    assert (app_root / "src" / "app" / "page.tsx").is_file()
    assert (app_root / "scripts" / "smoke.mjs").is_file()
    contract = GeneratedAppContract.model_validate_json(
        contract_path.read_text(encoding="utf-8"),
    )
    assert contract.stack == ["Next.js", "TypeScript", "Tailwind CSS"]
    assert contract.minimum_runnable_check == "npm test"
    assert Path(contract.output_root).is_absolute()
    command_manifest = TypeAdapter(list[GeneratedAppCommand]).validate_json(
        manifest_path.read_text(encoding="utf-8"),
    )
    assert any(command.name == "test" for command in command_manifest)
    verified = Signal2ShipWorkflowResult.model_validate_json(verify_result.output)
    assert verified.status == "verified"
    assert verified.run_state == "verified"
    verification = VerificationRecord.model_validate_json(
        verification_record_path.read_text(encoding="utf-8"),
    )
    assert verification.status == "passed"
    assert verification.command_results[0].command == "npm test"
    bundled = Signal2ShipWorkflowResult.model_validate_json(bundle_result.output)
    assert bundled.status == "needs_deploy_approval"
    assert bundled.run_state == "needs_deploy_approval"
    policy_review_path = output_dir / "reviews" / "POLICY_READINESS.json"
    deployment_bundle_path = output_dir / "launch" / "DEPLOYMENT_BUNDLE.json"
    policy_review = PolicyReadinessReview.model_validate_json(
        policy_review_path.read_text(encoding="utf-8"),
    )
    deployment_bundle = DeploymentReadinessBundle.model_validate_json(
        deployment_bundle_path.read_text(encoding="utf-8"),
    )
    assert len(policy_review.source_refresh_date) == 10
    assert any("apple.com" in str(url) for url in policy_review.official_source_urls)
    assert deployment_bundle.deploy_approval_required
    assert "store submission" in deployment_bundle.forbidden_without_approval
    assert "No deployment" in (
        output_dir / "launch" / "OCI_PREVIEW_BUNDLE.md"
    ).read_text(encoding="utf-8")
    store_workflow = Signal2ShipWorkflowResult.model_validate_json(
        store_pack_result.output,
    )
    store_pack_path = output_dir / "store" / "STORE_PACK.json"
    store_pack = StorePack.model_validate_json(
        store_pack_path.read_text(encoding="utf-8"),
    )
    assert store_workflow.status == "needs_store_metadata"
    assert store_workflow.store_pack == str(store_pack_path)
    assert store_pack.status == "blocked"
    assert any("app_type=web" in blocker for blocker in store_pack.blockers)
    assert "No App Store Connect" in (
        output_dir / "store" / "STORE_PACK.md"
    ).read_text(encoding="utf-8")


def test_build_approved_rejects_edited_spec_after_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    runner = CliRunner()
    raw_file = tmp_path / "last30days.md"
    output_dir = tmp_path / "outputs"
    app_dir = tmp_path / "apps" / "generated"
    approval_path = output_dir / "product" / "SPEC_APPROVAL.json"
    spec_packet = output_dir / "product" / "IDEA_SPEC_APPROVAL.json"
    _ = raw_file.write_text(make_last30days_markdown(), encoding="utf-8")
    monkeypatch.setattr(
        "signal2ship.cli.build_openrouter_client",
        _build_static_llm_client,
    )
    _ = runner.invoke(
        app,
        [
            "run",
            "AI coding agent workflow pain",
            "--raw-file",
            str(raw_file),
            "--output-dir",
            str(output_dir),
            "--app-dir",
            str(app_dir),
        ],
    )
    approve_result = runner.invoke(
        app,
        [
            "approve-spec",
            str(spec_packet),
            "--output",
            str(approval_path),
        ],
    )
    with spec_packet.open("a", encoding="utf-8") as file:
        _ = file.write("\n")

    # When
    build_result = runner.invoke(
        app,
        [
            "build-approved",
            str(approval_path),
            "--output-dir",
            str(output_dir),
            "--app-dir",
            str(app_dir),
        ],
    )

    # Then
    assert approve_result.exit_code == 0, approve_result.output
    assert build_result.exit_code == 1
    assert "content hash" in build_result.output
    assert not app_dir.exists()


def test_build_approved_refuses_to_overwrite_existing_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    runner = CliRunner()
    raw_file = tmp_path / "last30days.md"
    output_dir = tmp_path / "outputs"
    app_dir = tmp_path / "apps" / "generated"
    approval_path = output_dir / "product" / "SPEC_APPROVAL.json"
    spec_packet = output_dir / "product" / "IDEA_SPEC_APPROVAL.json"
    _ = raw_file.write_text(make_last30days_markdown(), encoding="utf-8")
    monkeypatch.setattr(
        "signal2ship.cli.build_openrouter_client",
        _build_static_llm_client,
    )
    _ = runner.invoke(
        app,
        [
            "run",
            "AI coding agent workflow pain",
            "--raw-file",
            str(raw_file),
            "--output-dir",
            str(output_dir),
            "--app-dir",
            str(app_dir),
        ],
    )
    _ = runner.invoke(
        app,
        [
            "approve-spec",
            str(spec_packet),
            "--output",
            str(approval_path),
        ],
    )
    first_build = runner.invoke(
        app,
        [
            "build-approved",
            str(approval_path),
            "--output-dir",
            str(output_dir),
            "--app-dir",
            str(app_dir),
        ],
    )

    # When
    second_build = runner.invoke(
        app,
        [
            "build-approved",
            str(approval_path),
            "--output-dir",
            str(output_dir),
            "--app-dir",
            str(app_dir),
        ],
    )

    # Then
    assert first_build.exit_code == 0, first_build.output
    assert second_build.exit_code == 1
    assert "refusing to overwrite" in second_build.output


def test_verify_app_records_failed_minimum_check(tmp_path: Path) -> None:
    # Given
    runner = CliRunner()
    output_dir = tmp_path / "outputs"
    app_root = tmp_path / "apps" / "generated" / "broken-app"
    smoke_script = app_root / "scripts" / "smoke.mjs"
    contract_path = app_root / "APP_CONTRACT.json"
    (app_root / "scripts").mkdir(parents=True)
    _ = (app_root / "package.json").write_text(
        '{"scripts":{"test":"node scripts/smoke.mjs"}}',
        encoding="utf-8",
    )
    _ = smoke_script.write_text("process.exit(1);\n", encoding="utf-8")
    contract = GeneratedAppContract(
        run_id="run_broken",
        app_type="web",
        output_root=str(app_root),
        stack=["Next.js", "TypeScript", "Tailwind CSS"],
        package_manager="npm",
        commands=[
            GeneratedAppCommand(
                name="test",
                command="npm test",
                required=True,
                purpose="Run smoke check.",
            ),
        ],
        expected_artifacts=["package.json", "scripts/smoke.mjs"],
        minimum_runnable_check="npm test",
        preview_instructions=["Run npm test."],
        source_approval_packet="outputs/product/IDEA_SPEC_APPROVAL.json",
        source_approval_hash=("0" * 64),
        generator="test",
        generated_at="2026-06-09T10:00:00+09:00",
    )
    _ = contract_path.write_text(contract.model_dump_json(indent=2), encoding="utf-8")

    # When
    result = runner.invoke(
        app,
        [
            "verify-app",
            str(contract_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    # Then
    record_path = output_dir / "reviews" / "VERIFICATION_RECORD.json"
    assert result.exit_code == 1
    assert "minimum generated app check failed" in result.output
    record = VerificationRecord.model_validate_json(
        record_path.read_text(encoding="utf-8"),
    )
    assert record.status == "failed"
    assert record.command_results[0].exit_code == 1


def test_verify_app_records_missing_app_root(tmp_path: Path) -> None:
    # Given
    runner = CliRunner()
    output_dir = tmp_path / "outputs"
    app_root = tmp_path / "apps" / "generated" / "missing-app"
    contract_path = tmp_path / "APP_CONTRACT.json"
    contract = GeneratedAppContract(
        run_id="run_missing",
        app_type="web",
        output_root=str(app_root),
        stack=["Next.js", "TypeScript", "Tailwind CSS"],
        package_manager="npm",
        commands=[
            GeneratedAppCommand(
                name="test",
                command="npm test",
                required=True,
                purpose="Run smoke check.",
            ),
        ],
        expected_artifacts=["package.json", "scripts/smoke.mjs"],
        minimum_runnable_check="npm test",
        preview_instructions=["Run npm test."],
        source_approval_packet="outputs/product/IDEA_SPEC_APPROVAL.json",
        source_approval_hash=("0" * 64),
        generator="test",
        generated_at="2026-06-09T10:00:00+09:00",
    )
    _ = contract_path.write_text(contract.model_dump_json(indent=2), encoding="utf-8")

    # When
    result = runner.invoke(
        app,
        [
            "verify-app",
            str(contract_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    # Then
    record_path = output_dir / "reviews" / "VERIFICATION_RECORD.json"
    assert result.exit_code == 1
    assert "minimum generated app check failed" in result.output
    record = VerificationRecord.model_validate_json(
        record_path.read_text(encoding="utf-8"),
    )
    assert record.status == "failed"
    assert "does not exist" in record.command_results[0].stderr_summary


def test_run_cli_stops_before_build_when_evidence_gate_fails(tmp_path: Path) -> None:
    # Given
    runner = CliRunner()
    output_dir = tmp_path / "outputs"
    app_dir = tmp_path / "apps" / "generated"
    raw_file = tmp_path / "thin_research.md"
    _ = raw_file.write_text(
        make_last30days_markdown(signal_count=1),
        encoding="utf-8",
    )

    # When
    result = runner.invoke(
        app,
        [
            "run",
            "AI coding agent workflow pain",
            "--raw-file",
            str(raw_file),
            "--output-dir",
            str(output_dir),
            "--app-dir",
            str(app_dir),
        ],
    )

    # Then
    assert result.exit_code == 0
    workflow = Signal2ShipWorkflowResult.model_validate_json(result.output)
    assert workflow.status == "request_more_research"
    assert workflow.selected_opportunity is None
    assert (output_dir / "signals" / "evidence_ledger.json").is_file()
    assert not app_dir.exists()


def test_run_cli_requires_openrouter_key_by_default_for_raw_research(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    runner = CliRunner()
    raw_file = tmp_path / "last30days.md"
    _ = raw_file.write_text(make_last30days_markdown(), encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_FLASH_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_PRO_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL_PRO", raising=False)
    monkeypatch.chdir(tmp_path)

    # When
    result = runner.invoke(
        app,
        [
            "run",
            "AI coding agent workflow pain",
            "--raw-file",
            str(raw_file),
            "--output-dir",
            str(tmp_path / "outputs"),
            "--app-dir",
            str(tmp_path / "apps" / "generated"),
            "--llm-model",
            "openai/gpt-5.2",
        ],
    )

    # Then
    assert result.exit_code == 1
    assert "missing OPENROUTER_API_KEY" in result.output
    assert "Traceback" not in result.output


def _build_static_llm_client(*, model_override: str | None = None) -> StaticLLMClient:
    _ = model_override
    return StaticLLMClient()
