from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest

from signal2ship.models import (
    GeneratedAppCommand,
    GeneratedAppContract,
    RunState,
    StoreMetadataInput,
    StorePack,
    VerificationCommandResult,
    VerificationRecord,
)
from signal2ship.release import (
    DeploymentReadinessError,
    StorePackError,
    generate_store_pack,
    prepare_deployment_readiness_bundle,
)


def test_prepare_deployment_bundle_rejects_mismatched_verification_run_id(
    tmp_path: Path,
) -> None:
    # Given
    contract_path = _write_contract(tmp_path, run_id="run_001")
    verification_path = _write_verification(tmp_path, run_id="run_other")

    # When / Then
    with pytest.raises(DeploymentReadinessError, match="run_id"):
        _ = prepare_deployment_readiness_bundle(
            app_contract_path=contract_path,
            verification_record_path=verification_path,
            output_dir=tmp_path / "outputs",
        )

    assert not (tmp_path / "outputs" / "launch" / "DEPLOYMENT_BUNDLE.json").exists()


def test_prepare_deployment_bundle_rejects_mismatched_app_root(
    tmp_path: Path,
) -> None:
    # Given
    contract_path = _write_contract(tmp_path, app_root=tmp_path / "apps" / "one")
    verification_path = _write_verification(
        tmp_path,
        app_root=tmp_path / "apps" / "two",
    )

    # When / Then
    with pytest.raises(DeploymentReadinessError, match="app_root"):
        _ = prepare_deployment_readiness_bundle(
            app_contract_path=contract_path,
            verification_record_path=verification_path,
            output_dir=tmp_path / "outputs",
        )

    assert not (tmp_path / "outputs" / "launch" / "DEPLOYMENT_BUNDLE.json").exists()


def test_prepare_deployment_bundle_rejects_inconsistent_passed_record(
    tmp_path: Path,
) -> None:
    # Given
    contract_path = _write_contract(tmp_path)
    verification_path = _write_verification(
        tmp_path,
        command_status="failed",
        command_exit_code=1,
    )

    # When / Then
    with pytest.raises(DeploymentReadinessError, match="command results"):
        _ = prepare_deployment_readiness_bundle(
            app_contract_path=contract_path,
            verification_record_path=verification_path,
            output_dir=tmp_path / "outputs",
        )

    assert not (tmp_path / "outputs" / "launch" / "DEPLOYMENT_BUNDLE.json").exists()


def test_prepare_deployment_bundle_requires_minimum_runnable_check(
    tmp_path: Path,
) -> None:
    # Given
    contract_path = _write_contract(tmp_path)
    verification_path = _write_verification(
        tmp_path,
        command="npm run lint",
    )

    # When / Then
    with pytest.raises(DeploymentReadinessError, match="minimum runnable check"):
        _ = prepare_deployment_readiness_bundle(
            app_contract_path=contract_path,
            verification_record_path=verification_path,
            output_dir=tmp_path / "outputs",
        )

    assert not (tmp_path / "outputs" / "launch" / "DEPLOYMENT_BUNDLE.json").exists()


def test_generate_store_pack_with_missing_metadata_records_blockers(
    tmp_path: Path,
) -> None:
    # Given
    contract_path = _write_contract(tmp_path)
    verification_path = _write_verification(tmp_path)

    # When
    result = generate_store_pack(
        app_contract_path=contract_path,
        verification_record_path=verification_path,
        output_dir=tmp_path / "outputs",
    )

    # Then
    store_pack_path = tmp_path / "outputs" / "store" / "STORE_PACK.json"
    store_pack_markdown_path = tmp_path / "outputs" / "store" / "STORE_PACK.md"
    assert result.status == "needs_store_metadata"
    assert result.run_state == RunState.NEEDS_STORE_METADATA
    assert result.store_pack == str(store_pack_path)
    assert store_pack_path.is_file()
    assert store_pack_markdown_path.is_file()
    store_pack = StorePack.model_validate_json(
        store_pack_path.read_text(encoding="utf-8"),
    )
    assert store_pack.status == "blocked"
    assert {section.platform for section in store_pack.platform_sections} == {
        "apple_app_store",
        "google_play",
    }
    assert any("app_type=web" in blocker for blocker in store_pack.blockers)
    assert any("apple.com" in url for url in store_pack.official_source_urls)
    assert "App Store Connect submission" in store_pack.forbidden_without_approval
    markdown = store_pack_markdown_path.read_text(encoding="utf-8")
    assert "No App Store Connect or Google Play Console submission" in markdown
    assert "not store approval" in markdown


def test_generate_store_pack_with_complete_mobile_metadata_still_needs_approval(
    tmp_path: Path,
) -> None:
    # Given
    contract_path = _write_contract(tmp_path, app_type="mobile")
    verification_path = _write_verification(tmp_path)
    metadata_path = tmp_path / "store-metadata.json"
    _ = metadata_path.write_text(
        _complete_store_metadata().model_dump_json(indent=2),
        encoding="utf-8",
    )

    # When
    result = generate_store_pack(
        app_contract_path=contract_path,
        verification_record_path=verification_path,
        metadata_path=metadata_path,
        output_dir=tmp_path / "outputs",
    )

    # Then
    store_pack_path = tmp_path / "outputs" / "store" / "STORE_PACK.json"
    store_pack = StorePack.model_validate_json(
        store_pack_path.read_text(encoding="utf-8"),
    )
    assert result.status == "needs_store_submission_approval"
    assert result.run_state == RunState.NEEDS_STORE_SUBMISSION_APPROVAL
    assert store_pack.status == "metadata_complete_needs_submission_approval"
    assert store_pack.blockers == []
    assert store_pack.app_type == "mobile"
    assert "Google Play Console submission" in store_pack.forbidden_without_approval


def test_generate_store_pack_rejects_malformed_metadata(tmp_path: Path) -> None:
    # Given
    contract_path = _write_contract(tmp_path, app_type="mobile")
    verification_path = _write_verification(tmp_path)
    metadata_path = tmp_path / "store-metadata.json"
    _ = metadata_path.write_text(
        '{"schema_version":"store_metadata.v2"}',
        encoding="utf-8",
    )

    # When / Then
    with pytest.raises(StorePackError, match="invalid store metadata"):
        _ = generate_store_pack(
            app_contract_path=contract_path,
            verification_record_path=verification_path,
            metadata_path=metadata_path,
            output_dir=tmp_path / "outputs",
        )
    assert not (tmp_path / "outputs" / "store" / "STORE_PACK.json").exists()


def test_generate_store_pack_rejects_invalid_metadata_urls_and_email(
    tmp_path: Path,
) -> None:
    # Given
    contract_path = _write_contract(tmp_path, app_type="mobile")
    verification_path = _write_verification(tmp_path)
    metadata_path = tmp_path / "store-metadata.json"
    _ = metadata_path.write_text(
        """
        {
          "listing": {
            "app_name": "Demo",
            "short_description": "Short",
            "full_description": "Full",
            "category": "Productivity",
            "support_url": "not-a-url",
            "contact_email": "not-email"
          },
          "privacy": {
            "privacy_policy_url": "not-a-url",
            "data_inventory": ["No user data collected."],
            "sdk_inventory": ["No third-party SDKs."],
            "collects_user_data": false,
            "shares_user_data": false,
            "tracking_enabled": false,
            "account_creation": false,
            "permissions": ["No permissions requested."]
          }
        }
        """,
        encoding="utf-8",
    )

    # When / Then
    with pytest.raises(StorePackError, match="invalid store metadata"):
        _ = generate_store_pack(
            app_contract_path=contract_path,
            verification_record_path=verification_path,
            metadata_path=metadata_path,
            output_dir=tmp_path / "outputs",
        )
    assert not (tmp_path / "outputs" / "store" / "STORE_PACK.json").exists()


def test_generate_store_pack_blocks_blank_inventory_values(
    tmp_path: Path,
) -> None:
    # Given
    contract_path = _write_contract(tmp_path, app_type="mobile")
    verification_path = _write_verification(tmp_path)
    metadata = _complete_store_metadata().model_dump(mode="json")
    metadata["privacy"] = {
        "privacy_policy_url": "https://example.com/privacy",
        "data_inventory": [" ", ""],
        "sdk_inventory": [" "],
        "collects_user_data": False,
        "shares_user_data": False,
        "tracking_enabled": False,
        "account_creation": False,
        "permissions": [" "],
    }
    metadata_path = tmp_path / "store-metadata.json"
    _ = metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # When
    result = generate_store_pack(
        app_contract_path=contract_path,
        verification_record_path=verification_path,
        metadata_path=metadata_path,
        output_dir=tmp_path / "outputs",
    )

    # Then
    store_pack_path = tmp_path / "outputs" / "store" / "STORE_PACK.json"
    store_pack = StorePack.model_validate_json(
        store_pack_path.read_text(encoding="utf-8"),
    )
    assert result.status == "needs_store_metadata"
    assert result.run_state == RunState.NEEDS_STORE_METADATA
    assert store_pack.status == "blocked"
    assert any("Data safety inventory" in blocker for blocker in store_pack.blockers)
    assert any("Third-party SDK" in blocker for blocker in store_pack.blockers)


def test_generate_store_pack_rejects_mismatched_verification(
    tmp_path: Path,
) -> None:
    # Given
    contract_path = _write_contract(tmp_path, run_id="run_001")
    verification_path = _write_verification(tmp_path, run_id="run_other")

    # When / Then
    with pytest.raises(DeploymentReadinessError, match="run_id"):
        _ = generate_store_pack(
            app_contract_path=contract_path,
            verification_record_path=verification_path,
            output_dir=tmp_path / "outputs",
        )
    assert not (tmp_path / "outputs" / "store" / "STORE_PACK.json").exists()


def _write_contract(
    tmp_path: Path,
    *,
    run_id: str = "run_001",
    app_root: Path | None = None,
    app_type: Literal["web", "mobile", "cli", "api", "mixed"] = "web",
) -> Path:
    root = app_root or tmp_path / "apps" / "generated" / "demo"
    contract = GeneratedAppContract(
        run_id=run_id,
        app_type=app_type,
        output_root=str(root),
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
    path = tmp_path / "APP_CONTRACT.json"
    _ = path.write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    return path


def _complete_store_metadata() -> StoreMetadataInput:
    return StoreMetadataInput.model_validate(
        {
            "listing": {
                "app_name": "Demo App",
                "short_description": "Short description.",
                "full_description": "Full description for store review.",
                "category": "Productivity",
                "support_url": "https://example.com/support",
                "contact_email": "support@example.com",
            },
            "privacy": {
                "privacy_policy_url": "https://example.com/privacy",
                "data_inventory": ["No user data collected."],
                "sdk_inventory": ["No third-party SDKs."],
                "collects_user_data": False,
                "shares_user_data": False,
                "tracking_enabled": False,
                "account_creation": False,
                "permissions": ["No permissions requested."],
            },
            "review": {
                "demo_account_required": False,
                "backend_required": False,
            },
            "assets": {
                "app_icon_ready": True,
                "screenshots_ready": True,
                "promotional_assets_ready": True,
            },
            "commerce": {
                "payments_enabled": False,
                "in_app_purchases": False,
                "ads_enabled": False,
                "target_age_range": "General audience",
                "content_rating_notes": "No restricted content.",
            },
        },
    )


def _write_verification(  # noqa: PLR0913
    tmp_path: Path,
    *,
    run_id: str = "run_001",
    app_root: Path | None = None,
    command_status: Literal["passed", "failed"] = "passed",
    command_exit_code: int = 0,
    command: str = "npm test",
) -> Path:
    root = app_root or tmp_path / "apps" / "generated" / "demo"
    verification = VerificationRecord(
        run_id=run_id,
        app_root=str(root),
        generated_at="2026-06-09",
        status="passed",
        command_results=[
            VerificationCommandResult(
                name="minimum_runnable_check",
                command=command,
                exit_code=command_exit_code,
                status=command_status,
                stdout_summary="ok",
                stderr_summary="",
                residual_risk="test fixture",
            ),
        ],
        residual_risks=[],
    )
    path = tmp_path / "VERIFICATION_RECORD.json"
    _ = path.write_text(verification.model_dump_json(indent=2), encoding="utf-8")
    return path
