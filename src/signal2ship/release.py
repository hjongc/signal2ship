from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, override

from pydantic import ValidationError

from .lifecycle import require_transition
from .models import (
    DeploymentReadinessBundle,
    GeneratedAppContract,
    PolicyReadinessReview,
    RunState,
    Signal2ShipWorkflowResult,
    StoreChecklistItem,
    StoreMetadataInput,
    StorePack,
    StorePlatformSection,
    VerificationCommandResult,
    VerificationRecord,
)

VERIFICATION_RECORD_FILENAME: Final = "VERIFICATION_RECORD.json"
POLICY_REVIEW_FILENAME: Final = "POLICY_READINESS.json"
POLICY_REVIEW_MARKDOWN: Final = "POLICY_READINESS.md"
DEPLOYMENT_BUNDLE_FILENAME: Final = "DEPLOYMENT_BUNDLE.json"
OCI_PREVIEW_BUNDLE_FILENAME: Final = "OCI_PREVIEW_BUNDLE.md"
STORE_PACK_FILENAME: Final = "STORE_PACK.json"
STORE_PACK_MARKDOWN: Final = "STORE_PACK.md"
MINIMUM_CHECK_COMMAND: Final = "npm test"
CHECK_TIMEOUT_SECONDS: Final = 60
OFFICIAL_POLICY_SOURCE_URLS: Final = [
    "https://developer.apple.com/app-store/review/guidelines/",
    "https://developer.apple.com/app-store/app-privacy-details/",
    "https://support.google.com/googleplay/android-developer/answer/10787469",
    "https://support.google.com/googleplay/android-developer/answer/10144311",
    "https://support.google.com/googleplay/android-developer/answer/13327111",
]
APPLE_POLICY_SOURCE_URLS: Final = OFFICIAL_POLICY_SOURCE_URLS[:2]
GOOGLE_POLICY_SOURCE_URLS: Final = OFFICIAL_POLICY_SOURCE_URLS[2:]
STORE_FORBIDDEN_WITHOUT_APPROVAL: Final = [
    "App Store Connect submission",
    "Google Play Console submission",
    "production deployment",
    "payment or in-app-purchase activation",
    "public launch posting",
    "credential lookup or store-account access",
    "real user data collection",
]


@dataclass(frozen=True, slots=True)
class AppVerificationError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"app verification error: {self.detail}"


@dataclass(frozen=True, slots=True)
class DeploymentReadinessError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"deployment readiness error: {self.detail}"


@dataclass(frozen=True, slots=True)
class StorePackError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"store pack error: {self.detail}"


def verify_generated_app(
    *,
    app_contract_path: Path,
    output_dir: Path,
) -> Signal2ShipWorkflowResult:
    contract = _load_contract(app_contract_path)
    app_root = Path(contract.output_root)
    if contract.minimum_runnable_check != MINIMUM_CHECK_COMMAND:
        raise AppVerificationError(
            detail=(
                "generated app contract minimum_runnable_check must be "
                f"{MINIMUM_CHECK_COMMAND}"
            ),
        )

    require_transition(RunState.CREATING_APP, RunState.VERIFIED)
    command_result = _run_minimum_check(app_root)
    status = "passed" if command_result.status == "passed" else "failed"
    record = VerificationRecord(
        run_id=contract.run_id,
        app_root=str(app_root),
        generated_at=_today_utc(),
        status=status,
        command_results=[command_result],
        residual_risks=[
            (
                "Only the dependency-free generated smoke check has run. "
                "Install, lint, typecheck, build, and browser checks remain "
                "required before deployment approval."
            ),
        ],
    )
    record_path = output_dir / "reviews" / VERIFICATION_RECORD_FILENAME
    _write_text(record_path, record.model_dump_json(indent=2))

    if record.status != "passed":
        raise AppVerificationError(
            detail=f"minimum generated app check failed; see {record_path}",
        )

    return Signal2ShipWorkflowResult(
        status="verified",
        selected_opportunity=app_root.name,
        artifacts=[str(record_path)],
        output_dir=str(output_dir),
        app_dir=str(app_root),
        reason="Generated app minimum runnable check passed.",
        run_id=contract.run_id,
        run_state=RunState.VERIFIED,
        app_contract=str(app_contract_path),
        verification_record=str(record_path),
    )


def prepare_deployment_readiness_bundle(
    *,
    app_contract_path: Path,
    verification_record_path: Path,
    output_dir: Path,
    target: str = "oci_preview",
) -> Signal2ShipWorkflowResult:
    contract = _load_contract(app_contract_path)
    verification = _load_verification_record(verification_record_path)
    _require_verification_matches_contract(
        verification,
        contract,
        artifact_name="deployment bundle",
    )

    require_transition(RunState.VERIFIED, RunState.BUNDLE_READY)
    require_transition(RunState.BUNDLE_READY, RunState.NEEDS_DEPLOY_APPROVAL)

    policy_review = _build_policy_review(contract)
    policy_review_path = output_dir / "reviews" / POLICY_REVIEW_FILENAME
    policy_markdown_path = output_dir / "reviews" / POLICY_REVIEW_MARKDOWN
    deployment_bundle = DeploymentReadinessBundle(
        run_id=contract.run_id,
        state=RunState.NEEDS_DEPLOY_APPROVAL,
        target=target,
        app_root=contract.output_root,
        verification_record_path=str(verification_record_path),
        policy_review_path=str(policy_review_path),
        deploy_approval_required=True,
        forbidden_without_approval=[
            "production deployment",
            "store submission",
            "payment activation",
            "public launch posting",
            "real user data collection",
        ],
        next_required_action=(
            "Ask the operator for explicit deployment or store-submission "
            "approval before running any release command."
        ),
    )
    deployment_bundle_path = output_dir / "launch" / DEPLOYMENT_BUNDLE_FILENAME
    oci_bundle_path = output_dir / "launch" / OCI_PREVIEW_BUNDLE_FILENAME

    _write_text(policy_review_path, policy_review.model_dump_json(indent=2))
    _write_text(policy_markdown_path, _render_policy_review(policy_review))
    _write_text(deployment_bundle_path, deployment_bundle.model_dump_json(indent=2))
    _write_text(oci_bundle_path, _render_deployment_bundle(deployment_bundle))

    return Signal2ShipWorkflowResult(
        status="needs_deploy_approval",
        selected_opportunity=Path(contract.output_root).name,
        artifacts=[
            str(policy_review_path),
            str(policy_markdown_path),
            str(deployment_bundle_path),
            str(oci_bundle_path),
        ],
        output_dir=str(output_dir),
        app_dir=contract.output_root,
        reason=(
            "Deployment readiness bundle prepared. No deployment or store "
            "submission was executed; explicit approval is required next."
        ),
        run_id=contract.run_id,
        run_state=RunState.NEEDS_DEPLOY_APPROVAL,
        app_contract=str(app_contract_path),
        verification_record=str(verification_record_path),
        policy_review=str(policy_review_path),
        deployment_bundle=str(deployment_bundle_path),
    )


def generate_store_pack(
    *,
    app_contract_path: Path,
    verification_record_path: Path,
    output_dir: Path,
    metadata_path: Path | None = None,
) -> Signal2ShipWorkflowResult:
    contract = _load_contract(app_contract_path)
    verification = _load_verification_record(verification_record_path)
    _require_verification_matches_contract(
        verification,
        contract,
        artifact_name="store pack",
    )
    metadata = _load_store_metadata(metadata_path)
    store_pack = _build_store_pack(contract, metadata)
    run_state = (
        RunState.NEEDS_STORE_METADATA
        if store_pack.status == "blocked"
        else RunState.NEEDS_STORE_SUBMISSION_APPROVAL
    )
    require_transition(RunState.VERIFIED, run_state)
    store_pack_path = output_dir / "store" / STORE_PACK_FILENAME
    store_pack_markdown_path = output_dir / "store" / STORE_PACK_MARKDOWN

    _write_text(store_pack_path, store_pack.model_dump_json(indent=2))
    _write_text(store_pack_markdown_path, _render_store_pack(store_pack))

    result_status = (
        "needs_store_metadata"
        if store_pack.status == "blocked"
        else "needs_store_submission_approval"
    )
    reason = (
        (
            _join_text(
                "Store pack generated with blockers. No store submission, ",
                "deployment, payment activation, credential lookup, or ",
                "real user data collection was executed.",
            )
        )
        if store_pack.status == "blocked"
        else (
            _join_text(
                "Store metadata pack generated. Submission approval is still ",
                "required before any App Store Connect or Google Play ",
                "Console action.",
            )
        )
    )
    return Signal2ShipWorkflowResult(
        status=result_status,
        selected_opportunity=Path(contract.output_root).name,
        artifacts=[str(store_pack_path), str(store_pack_markdown_path)],
        output_dir=str(output_dir),
        app_dir=contract.output_root,
        reason=reason,
        run_id=contract.run_id,
        run_state=run_state,
        app_contract=str(app_contract_path),
        verification_record=str(verification_record_path),
        store_pack=str(store_pack_path),
    )


def _run_minimum_check(app_root: Path) -> VerificationCommandResult:
    npm_path = shutil.which("npm")
    if npm_path is None:
        raise AppVerificationError(detail="required executable not found: npm")

    if not app_root.is_dir():
        return VerificationCommandResult(
            name="minimum_runnable_check",
            command=MINIMUM_CHECK_COMMAND,
            exit_code=-1,
            status="failed",
            stdout_summary="",
            stderr_summary=f"generated app root does not exist: {app_root}",
            residual_risk="The generated app directory is missing.",
        )

    try:
        completed = subprocess.run(  # noqa: S603
            [npm_path, "test"],
            cwd=app_root,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError as error:
        return VerificationCommandResult(
            name="minimum_runnable_check",
            command=MINIMUM_CHECK_COMMAND,
            exit_code=-1,
            status="failed",
            stdout_summary="",
            stderr_summary=str(error),
            residual_risk="The generated app smoke check could not start.",
        )
    except subprocess.TimeoutExpired as error:
        return VerificationCommandResult(
            name="minimum_runnable_check",
            command=MINIMUM_CHECK_COMMAND,
            exit_code=-1,
            status="failed",
            stdout_summary=_summarize(error.stdout),
            stderr_summary=_summarize(error.stderr),
            residual_risk="The generated app smoke check timed out.",
        )

    status = "passed" if completed.returncode == 0 else "failed"
    return VerificationCommandResult(
        name="minimum_runnable_check",
        command=MINIMUM_CHECK_COMMAND,
        exit_code=completed.returncode,
        status=status,
        stdout_summary=_summarize(completed.stdout),
        stderr_summary=_summarize(completed.stderr),
        residual_risk=(
            "This check verifies generated files only; it does not replace "
            "full app install, build, or browser verification."
        ),
    )


def _require_verification_matches_contract(
    verification: VerificationRecord,
    contract: GeneratedAppContract,
    *,
    artifact_name: str,
) -> None:
    if verification.status != "passed":
        raise DeploymentReadinessError(
            detail=f"{artifact_name} requires a passed verification record",
        )

    if verification.run_id != contract.run_id:
        raise DeploymentReadinessError(
            detail=(
                "verification record run_id does not match generated app contract"
            ),
        )

    if _canonical_path(verification.app_root) != _canonical_path(contract.output_root):
        raise DeploymentReadinessError(
            detail=(
                "verification record app_root does not match generated app contract"
            ),
        )

    failed_results = [
        result
        for result in verification.command_results
        if result.status != "passed" or result.exit_code != 0
    ]
    if failed_results:
        raise DeploymentReadinessError(
            detail=(
                "verification record contains failed or non-zero command results"
            ),
        )

    has_minimum_check = any(
        result.command == contract.minimum_runnable_check
        for result in verification.command_results
    )
    if not has_minimum_check:
        raise DeploymentReadinessError(
            detail=(
                "verification record does not include the contract minimum "
                "runnable check"
            ),
        )


def _load_store_metadata(path: Path | None) -> StoreMetadataInput:
    if path is None:
        return StoreMetadataInput()
    try:
        return StoreMetadataInput.model_validate_json(_read_text(path))
    except ValidationError as error:
        raise StorePackError(detail=f"invalid store metadata: {path}") from error


def _build_store_pack(
    contract: GeneratedAppContract,
    metadata: StoreMetadataInput,
) -> StorePack:
    platform_sections = [
        _build_apple_section(contract, metadata),
        _build_google_section(contract, metadata),
    ]
    blockers = [
        blocker
        for section in platform_sections
        for blocker in section.blockers
    ]
    if contract.app_type == "web":
        blockers.append(
            _join_text(
                "Generated app contract app_type=web is not a native or ",
                "mobile store package; add validated iOS/Android packaging ",
                "before submission work.",
            ),
        )
    elif contract.app_type not in {"mobile", "mixed"}:
        blockers.append(
            "".join(
                (
                    f"Generated app contract app_type={contract.app_type} is ",
                    "not a mobile store package.",
                ),
            ),
        )

    return StorePack(
        run_id=contract.run_id,
        schema_version="store_pack.v1",
        metadata_schema_version=metadata.schema_version,
        status=(
            "blocked"
            if blockers
            else "metadata_complete_needs_submission_approval"
        ),
        app_root=contract.output_root,
        app_type=contract.app_type,
        official_source_urls=OFFICIAL_POLICY_SOURCE_URLS,
        source_refresh_date=_today_utc(),
        platform_sections=platform_sections,
        blockers=blockers,
        forbidden_without_approval=STORE_FORBIDDEN_WITHOUT_APPROVAL,
        next_required_action=(
            "Resolve blockers and ask the operator for explicit store-submission "
            "approval before opening App Store Connect or Google Play Console."
        ),
        disclaimer=(
            "This store pack is a preparation artifact only. It is not legal "
            "advice, not a compliance guarantee, and not evidence of Apple App "
            "Store or Google Play approval."
        ),
    )


def _build_apple_section(
    contract: GeneratedAppContract,
    metadata: StoreMetadataInput,
) -> StorePlatformSection:
    checklist = [
        _required_text_item(
            "apple_listing_name",
            "App name",
            metadata.listing.app_name,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _required_text_item(
            "apple_listing_description",
            "Description or promotional text",
            metadata.listing.full_description,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _required_text_item(
            "apple_listing_category",
            "Category",
            metadata.listing.category,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _required_either_item(
            "apple_contact",
            "Support URL or contact email",
            [metadata.listing.support_url, metadata.listing.contact_email],
            APPLE_POLICY_SOURCE_URLS,
        ),
        _required_text_item(
            "apple_privacy_policy",
            "Privacy policy URL",
            metadata.privacy.privacy_policy_url,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _required_list_item(
            "apple_data_inventory",
            "App privacy data inventory",
            metadata.privacy.data_inventory,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _required_list_item(
            "apple_sdk_inventory",
            "Third-party SDK inventory",
            metadata.privacy.sdk_inventory,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _boolean_declaration_item(
            "apple_tracking",
            "Tracking declaration",
            metadata.privacy.tracking_enabled,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _account_deletion_item(
            "apple_account_deletion",
            metadata,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _conditional_text_item(
            "apple_demo_access",
            "Reviewer demo account or demo-mode instructions",
            required=metadata.review.demo_account_required,
            value=metadata.review.demo_account_instructions,
            source_urls=APPLE_POLICY_SOURCE_URLS,
        ),
        _conditional_text_item(
            "apple_backend_live",
            "Backend/service live status URL",
            required=metadata.review.backend_required,
            value=metadata.review.backend_status_url,
            source_urls=APPLE_POLICY_SOURCE_URLS,
        ),
        _asset_item(
            "apple_app_icon",
            "App icon asset",
            metadata.assets.app_icon_ready,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _asset_item(
            "apple_screenshots",
            "App Store screenshots",
            metadata.assets.screenshots_ready,
            APPLE_POLICY_SOURCE_URLS,
        ),
        _boolean_declaration_item(
            "apple_payments",
            "Payments or in-app purchases declaration",
            _declared_payments(metadata),
            APPLE_POLICY_SOURCE_URLS,
        ),
        _required_either_item(
            "apple_age_content",
            "Age or content rating notes",
            [
                metadata.commerce.target_age_range,
                metadata.commerce.content_rating_notes,
            ],
            APPLE_POLICY_SOURCE_URLS,
        ),
        _review_notes_for_iap_item(
            "apple_iap_review_notes",
            metadata,
            APPLE_POLICY_SOURCE_URLS,
        ),
    ]
    return StorePlatformSection(
        platform="apple_app_store",
        checklist=checklist,
        blockers=_blockers_from_checklist("Apple App Store", checklist),
        notes=[
            _join_text(
                "This section prepares review metadata only; it does not ",
                "submit to App Store Connect.",
            ),
            f"Contract app_type is {contract.app_type}.",
        ],
    )


def _build_google_section(
    contract: GeneratedAppContract,
    metadata: StoreMetadataInput,
) -> StorePlatformSection:
    checklist = [
        _required_text_item(
            "google_listing_name",
            "App name",
            metadata.listing.app_name,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _required_text_item(
            "google_short_description",
            "Short description",
            metadata.listing.short_description,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _required_text_item(
            "google_full_description",
            "Full description",
            metadata.listing.full_description,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _required_text_item(
            "google_category",
            "Category",
            metadata.listing.category,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _required_either_item(
            "google_contact",
            "Contact email or support URL",
            [metadata.listing.contact_email, metadata.listing.support_url],
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _required_text_item(
            "google_privacy_policy",
            "Privacy policy URL",
            metadata.privacy.privacy_policy_url,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _required_list_item(
            "google_data_safety_inventory",
            "Data safety inventory",
            metadata.privacy.data_inventory,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _boolean_declaration_item(
            "google_collects_user_data",
            "User data collection declaration",
            metadata.privacy.collects_user_data,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _boolean_declaration_item(
            "google_shares_user_data",
            "User data sharing declaration",
            metadata.privacy.shares_user_data,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _required_list_item(
            "google_sdk_inventory",
            "Third-party SDK data behavior inventory",
            metadata.privacy.sdk_inventory,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _required_list_item(
            "google_permissions",
            "Permissions and sensitive API inventory",
            metadata.privacy.permissions,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _account_deletion_item(
            "google_account_deletion",
            metadata,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _boolean_declaration_item(
            "google_ads",
            "Ads declaration",
            metadata.commerce.ads_enabled,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _required_either_item(
            "google_target_content",
            "Target audience or content notes",
            [
                metadata.commerce.target_age_range,
                metadata.commerce.content_rating_notes,
            ],
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _asset_item(
            "google_app_icon",
            "Google Play app icon asset",
            metadata.assets.app_icon_ready,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
        _asset_item(
            "google_screenshots",
            "Google Play screenshots",
            metadata.assets.screenshots_ready,
            GOOGLE_POLICY_SOURCE_URLS,
        ),
    ]
    return StorePlatformSection(
        platform="google_play",
        checklist=checklist,
        blockers=_blockers_from_checklist("Google Play", checklist),
        notes=[
            _join_text(
                "This section prepares Play Console metadata only; it does ",
                "not submit to Google Play Console.",
            ),
            f"Contract app_type is {contract.app_type}.",
        ],
    )


def _required_text_item(
    item_id: str,
    label: str,
    value: object | None,
    source_urls: list[str],
) -> StoreChecklistItem:
    if _has_text(value):
        return _checklist_item(item_id, label, "provided", "Provided.", source_urls)
    return _checklist_item(
        item_id,
        label,
        "missing",
        "Required metadata is missing.",
        source_urls,
    )


def _required_either_item(
    item_id: str,
    label: str,
    values: list[object | None],
    source_urls: list[str],
) -> StoreChecklistItem:
    if any(_has_text(value) for value in values):
        return _checklist_item(item_id, label, "provided", "Provided.", source_urls)
    return _checklist_item(
        item_id,
        label,
        "missing",
        "At least one required metadata value is missing.",
        source_urls,
    )


def _required_list_item(
    item_id: str,
    label: str,
    values: list[str],
    source_urls: list[str],
) -> StoreChecklistItem:
    if values:
        return _checklist_item(item_id, label, "provided", "Provided.", source_urls)
    return _checklist_item(
        item_id,
        label,
        "missing",
        "Required inventory is missing.",
        source_urls,
    )


def _boolean_declaration_item(
    item_id: str,
    label: str,
    value: bool | None,
    source_urls: list[str],
) -> StoreChecklistItem:
    if value is None:
        return _checklist_item(
            item_id,
            label,
            "missing",
            "Required yes/no declaration is missing.",
            source_urls,
        )
    return _checklist_item(
        item_id,
        label,
        "provided",
        f"Declared: {value}.",
        source_urls,
    )


def _conditional_text_item(
    item_id: str,
    label: str,
    *,
    required: bool | None,
    value: object | None,
    source_urls: list[str],
) -> StoreChecklistItem:
    if required is False:
        return _checklist_item(
            item_id,
            label,
            "not_applicable",
            "Declared not applicable.",
            source_urls,
        )
    if required is True and _has_text(value):
        return _checklist_item(item_id, label, "provided", "Provided.", source_urls)
    if required is True:
        return _checklist_item(
            item_id,
            label,
            "missing",
            "Declared required, but supporting metadata is missing.",
            source_urls,
        )
    return _checklist_item(
        item_id,
        label,
        "needs_review",
        "Applicability has not been declared.",
        source_urls,
    )


def _account_deletion_item(
    item_id: str,
    metadata: StoreMetadataInput,
    source_urls: list[str],
) -> StoreChecklistItem:
    if metadata.privacy.account_creation is False:
        return _checklist_item(
            item_id,
            "Account deletion paths",
            "not_applicable",
            "Account creation is declared not applicable.",
            source_urls,
        )
    has_deletion_paths = (
        _has_text(metadata.privacy.account_deletion_in_app_path)
        and _has_text(metadata.privacy.account_deletion_web_url)
    )
    if metadata.privacy.account_creation is True and has_deletion_paths:
        return _checklist_item(
            item_id,
            "Account deletion paths",
            "provided",
            "In-app and web deletion paths are provided.",
            source_urls,
        )
    if metadata.privacy.account_creation is True:
        return _checklist_item(
            item_id,
            "Account deletion paths",
            "missing",
            _join_text(
                "Account creation is declared, but in-app and web deletion ",
                "paths are incomplete.",
            ),
            source_urls,
        )
    return _checklist_item(
        item_id,
        "Account deletion paths",
        "needs_review",
        "Account creation applicability has not been declared.",
        source_urls,
    )


def _asset_item(
    item_id: str,
    label: str,
    value: bool | None,
    source_urls: list[str],
) -> StoreChecklistItem:
    if value is True:
        return _checklist_item(
            item_id,
            label,
            "provided",
            "Asset is declared prepared.",
            source_urls,
        )
    if value is False:
        return _checklist_item(
            item_id,
            label,
            "missing",
            "Asset is declared not prepared.",
            source_urls,
        )
    return _checklist_item(
        item_id,
        label,
        "missing",
        "Asset readiness is missing.",
        source_urls,
    )


def _review_notes_for_iap_item(
    item_id: str,
    metadata: StoreMetadataInput,
    source_urls: list[str],
) -> StoreChecklistItem:
    if (
        not metadata.commerce.in_app_purchases
        and not metadata.commerce.payments_enabled
    ):
        return _checklist_item(
            item_id,
            "Review notes for payments or IAP",
            "not_applicable",
            "Payments and IAP are not declared enabled.",
            source_urls,
        )
    if _has_text(metadata.review.review_notes):
        return _checklist_item(
            item_id,
            "Review notes for payments or IAP",
            "provided",
            "Review notes are provided.",
            source_urls,
        )
    return _checklist_item(
        item_id,
        "Review notes for payments or IAP",
        "missing",
        "Payments or IAP are declared enabled, but review notes are missing.",
        source_urls,
    )


def _declared_payments(metadata: StoreMetadataInput) -> bool | None:
    if (
        metadata.commerce.payments_enabled is None
        and metadata.commerce.in_app_purchases is None
    ):
        return None
    return bool(
        metadata.commerce.payments_enabled
        or metadata.commerce.in_app_purchases,
    )


def _checklist_item(
    item_id: str,
    label: str,
    status: Literal["provided", "missing", "not_applicable", "needs_review"],
    detail: str,
    source_urls: list[str],
) -> StoreChecklistItem:
    return StoreChecklistItem(
        item_id=item_id,
        label=label,
        status=status,
        detail=detail,
        source_urls=source_urls,
    )


def _blockers_from_checklist(
    platform: str,
    checklist: list[StoreChecklistItem],
) -> list[str]:
    return [
        f"{platform}: {item.label} - {item.detail}"
        for item in checklist
        if item.status in {"missing", "needs_review"}
    ]


def _render_store_pack(store_pack: StorePack) -> str:
    lines = [
        "# Store Pack",
        "",
        f"Run ID: `{store_pack.run_id}`",
        f"Status: `{store_pack.status}`",
        f"App type: `{store_pack.app_type}`",
        f"App root: `{store_pack.app_root}`",
        f"Source refresh date: {store_pack.source_refresh_date}",
        "",
        "No App Store Connect or Google Play Console submission has been executed.",
        "This artifact is not store approval and not a command to submit.",
        "",
        "## Official Sources",
        "",
        *[f"- {url}" for url in store_pack.official_source_urls],
        "",
        "## Blockers",
        "",
    ]
    lines.extend(
        [f"- {blocker}" for blocker in store_pack.blockers]
        if store_pack.blockers
        else ["- None recorded. Submission approval is still required."]
    )
    lines.extend(
        [
            "",
            "## Platform Sections",
            "",
        ],
    )
    for section in store_pack.platform_sections:
        lines.extend(
            [
                f"### {section.platform}",
                "",
                "#### Checklist",
                "",
            ],
        )
        lines.extend(
            [
                f"- `{item.status}` {item.label}: {item.detail}"
                for item in section.checklist
            ],
        )
        lines.extend(["", "#### Section Blockers", ""])
        lines.extend(
            [f"- {blocker}" for blocker in section.blockers]
            if section.blockers
            else ["- None recorded for metadata completeness."]
        )
        lines.extend(["", "#### Notes", ""])
        lines.extend([f"- {note}" for note in section.notes])
        lines.append("")
    lines.extend(
        [
            "## Forbidden Without Explicit Approval",
            "",
            *[f"- {item}" for item in store_pack.forbidden_without_approval],
            "",
            "## Next Required Action",
            "",
            store_pack.next_required_action,
            "",
            "## Disclaimer",
            "",
            store_pack.disclaimer,
            "",
        ],
    )
    return "\n".join(lines)


def _has_text(value: object | None) -> bool:
    return value is not None and str(value).strip() != ""


def _join_text(*parts: str) -> str:
    return "".join(parts)


def _build_policy_review(contract: GeneratedAppContract) -> PolicyReadinessReview:
    return PolicyReadinessReview(
        run_id=contract.run_id,
        official_source_urls=OFFICIAL_POLICY_SOURCE_URLS,
        source_refresh_date=_today_utc(),
        data_inventory=[
            "No real user data collection is declared for this generated preview.",
            "No account creation is declared for this generated preview.",
            "No tracking or analytics event collection is declared.",
        ],
        sdk_inventory=[
            "Next.js",
            "React",
            "React DOM",
            "No analytics, ads, payments, or mobile SDK is declared.",
        ],
        account_deletion_applicability=(
            "not_applicable_no_account_creation_declared"
        ),
        permissions_inventory=["No native mobile permissions declared."],
        payments_inventory=["No payments or in-app purchases declared."],
        reviewer_or_tool="signal2ship policy readiness pack v1",
        readiness_notes=[
            "Re-check Apple and Google policy sources before any store submission.",
            "Update data and SDK inventory if the generated app changes scope.",
            (
                "Add privacy policy and account deletion paths if accounts or "
                "user data enter scope."
            ),
        ],
        blockers=[
            "Explicit deployment or store-submission approval has not been granted.",
        ],
        disclaimer=(
            "This is a readiness review artifact, not legal advice and not a "
            "guarantee of App Store or Google Play approval."
        ),
    )


def _render_policy_review(review: PolicyReadinessReview) -> str:
    return "\n".join(
        [
            "# Policy Readiness Review",
            "",
            f"Run ID: `{review.run_id}`",
            f"Source refresh date: {review.source_refresh_date}",
            "",
            "## Official Sources",
            "",
            *[f"- {url}" for url in review.official_source_urls],
            "",
            "## Data Inventory",
            "",
            *[f"- {item}" for item in review.data_inventory],
            "",
            "## SDK Inventory",
            "",
            *[f"- {item}" for item in review.sdk_inventory],
            "",
            "## Blockers",
            "",
            *[f"- {item}" for item in review.blockers],
            "",
            "## Disclaimer",
            "",
            review.disclaimer,
            "",
        ],
    )


def _render_deployment_bundle(bundle: DeploymentReadinessBundle) -> str:
    return "\n".join(
        [
            "# Deployment Readiness Bundle",
            "",
            f"Run ID: `{bundle.run_id}`",
            f"Target: `{bundle.target}`",
            f"State: `{bundle.state.value}`",
            f"App root: `{bundle.app_root}`",
            "",
            "No deployment or store-submission command has been executed.",
            "Explicit operator approval is required before release actions.",
            "",
            "## Forbidden Without Approval",
            "",
            *[f"- {item}" for item in bundle.forbidden_without_approval],
            "",
            "## Next Required Action",
            "",
            bundle.next_required_action,
            "",
        ],
    )


def _load_contract(path: Path) -> GeneratedAppContract:
    try:
        return GeneratedAppContract.model_validate_json(_read_text(path))
    except ValidationError as error:
        raise AppVerificationError(
            detail=f"invalid generated app contract: {path}",
        ) from error


def _load_verification_record(path: Path) -> VerificationRecord:
    try:
        return VerificationRecord.model_validate_json(_read_text(path))
    except ValidationError as error:
        raise DeploymentReadinessError(
            detail=f"invalid verification record: {path}",
        ) from error


def _canonical_path(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise AppVerificationError(detail=f"required file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _summarize(output: str | bytes | None) -> str:
    if output is None:
        return ""
    text = (
        output.decode("utf-8", errors="replace")
        if isinstance(output, bytes)
        else output
    )
    return text.strip()[:1200]


def _today_utc() -> str:
    return datetime.now(tz=UTC).date().isoformat()
