from __future__ import annotations

from enum import StrEnum, unique
from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

DATE_PATTERN: Final = r"^\d{4}-\d{2}-\d{2}$"


@unique
class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@unique
class BusinessRelevance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FrozenModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class Engagement(FrozenModel):
    upvotes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    views: int | None = Field(default=None, ge=0)


class EvidenceSignal(FrozenModel):
    signal_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    url: HttpUrl
    observed_at: str = Field(pattern=DATE_PATTERN)
    audience: str = Field(min_length=1)
    pain_point: str = Field(min_length=1)
    evidence_summary: str = Field(min_length=1)
    engagement: Engagement = Field(default_factory=Engagement)
    business_relevance: BusinessRelevance
    confidence: Confidence
    validation_needed: str = Field(min_length=1)


class EvidenceLedger(FrozenModel):
    domain: str = Field(min_length=1)
    generated_at: str = Field(pattern=DATE_PATTERN)
    signals: list[EvidenceSignal]


@unique
class RunState(StrEnum):
    RESEARCHING = "researching"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NEEDS_SPEC_APPROVAL = "needs_spec_approval"
    SPEC_APPROVED = "spec_approved"
    CREATING_APP = "creating_app"
    VERIFICATION_FAILED = "verification_failed"
    VERIFIED = "verified"
    BUNDLE_READY = "bundle_ready"
    NEEDS_DEPLOY_APPROVAL = "needs_deploy_approval"
    NEEDS_STORE_METADATA = "needs_store_metadata"
    NEEDS_STORE_SUBMISSION_APPROVAL = "needs_store_submission_approval"


class ApprovalPacket(FrozenModel):
    run_id: str = Field(min_length=1)
    artifact_path: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_version: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    approved_at: str = Field(min_length=1)
    allowed_next_state: RunState
    approval_reason: str = Field(min_length=1)
    approval_notes: str | None = None


class IdeaSpecApprovalPacket(FrozenModel):
    run_id: str = Field(min_length=1)
    state: RunState
    topic: str = Field(min_length=1)
    idea: str = Field(min_length=1)
    opportunity_score: int = Field(ge=0, le=100)
    target_user: str = Field(min_length=1)
    core_problem: str = Field(min_length=1)
    mvp_scope: list[str] = Field(min_length=1)
    non_goals: list[str] = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    evidence_basis: list[str] = Field(min_length=1)
    evidence_signal_ids: list[str] = Field(min_length=1)
    policy_privacy_notes: list[str] = Field(min_length=1)
    generated_at: str = Field(pattern=DATE_PATTERN)
    approval_required: bool
    approved_app_creation_state: RunState


class GeneratedAppCommand(FrozenModel):
    name: str = Field(min_length=1)
    command: str = Field(min_length=1)
    required: bool
    purpose: str = Field(min_length=1)


class GeneratedAppContract(FrozenModel):
    run_id: str = Field(min_length=1)
    app_type: Literal["web", "mobile", "cli", "api", "mixed"]
    output_root: str = Field(min_length=1)
    stack: list[str] = Field(min_length=1)
    package_manager: str = Field(min_length=1)
    commands: list[GeneratedAppCommand] = Field(min_length=1)
    expected_artifacts: list[str] = Field(min_length=1)
    minimum_runnable_check: str = Field(min_length=1)
    preview_instructions: list[str] = Field(min_length=1)
    source_approval_packet: str = Field(min_length=1)
    source_approval_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    generator: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)


class VerificationCommandResult(FrozenModel):
    name: str = Field(min_length=1)
    command: str = Field(min_length=1)
    exit_code: int
    status: Literal["passed", "failed"]
    stdout_summary: str
    stderr_summary: str
    residual_risk: str = Field(min_length=1)


class VerificationRecord(FrozenModel):
    run_id: str = Field(min_length=1)
    app_root: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    status: Literal["passed", "failed"]
    command_results: list[VerificationCommandResult] = Field(min_length=1)
    residual_risks: list[str]


class PolicyReadinessReview(FrozenModel):
    run_id: str = Field(min_length=1)
    official_source_urls: list[str] = Field(min_length=1)
    source_refresh_date: str = Field(pattern=DATE_PATTERN)
    data_inventory: list[str]
    sdk_inventory: list[str]
    account_deletion_applicability: str = Field(min_length=1)
    permissions_inventory: list[str]
    payments_inventory: list[str]
    reviewer_or_tool: str = Field(min_length=1)
    readiness_notes: list[str] = Field(min_length=1)
    blockers: list[str]
    disclaimer: str = Field(min_length=1)


class DeploymentReadinessBundle(FrozenModel):
    run_id: str = Field(min_length=1)
    state: RunState
    target: str = Field(min_length=1)
    app_root: str = Field(min_length=1)
    verification_record_path: str = Field(min_length=1)
    policy_review_path: str = Field(min_length=1)
    deploy_approval_required: bool
    forbidden_without_approval: list[str] = Field(min_length=1)
    next_required_action: str = Field(min_length=1)


class StoreListingMetadata(FrozenModel):
    app_name: str | None = None
    subtitle: str | None = None
    short_description: str | None = None
    full_description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    category: str | None = None
    support_url: HttpUrl | None = None
    marketing_url: HttpUrl | None = None
    contact_email: str | None = Field(
        default=None,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )

    @field_validator("keywords", mode="after")
    @classmethod
    def strip_blank_keywords(cls, values: list[str]) -> list[str]:
        """Remove blank keyword placeholders before checklist evaluation."""
        return [value.strip() for value in values if value.strip()]


class StorePrivacyMetadata(FrozenModel):
    privacy_policy_url: HttpUrl | None = None
    data_inventory: list[str] = Field(default_factory=list)
    sdk_inventory: list[str] = Field(default_factory=list)
    collects_user_data: bool | None = None
    shares_user_data: bool | None = None
    tracking_enabled: bool | None = None
    account_creation: bool | None = None
    account_deletion_in_app_path: str | None = None
    account_deletion_web_url: HttpUrl | None = None
    permissions: list[str] = Field(default_factory=list)
    prominent_disclosure_required: bool | None = None
    prominent_disclosure_notes: str | None = None

    @field_validator(
        "data_inventory",
        "sdk_inventory",
        "permissions",
        mode="after",
    )
    @classmethod
    def strip_blank_inventory(cls, values: list[str]) -> list[str]:
        """Remove blank inventory placeholders before checklist evaluation."""
        return [value.strip() for value in values if value.strip()]


class StoreReviewMetadata(FrozenModel):
    demo_account_required: bool | None = None
    demo_account_instructions: str | None = None
    backend_required: bool | None = None
    backend_status_url: HttpUrl | None = None
    review_notes: str | None = None


class StoreAssetMetadata(FrozenModel):
    app_icon_ready: bool | None = None
    screenshots_ready: bool | None = None
    screenshot_device_notes: list[str] = Field(default_factory=list)
    promotional_assets_ready: bool | None = None


class StoreCommerceMetadata(FrozenModel):
    payments_enabled: bool | None = None
    in_app_purchases: bool | None = None
    ads_enabled: bool | None = None
    target_age_range: str | None = None
    content_rating_notes: str | None = None


class StoreMetadataInput(FrozenModel):
    schema_version: Literal["store_metadata.v1"] = "store_metadata.v1"
    listing: StoreListingMetadata = Field(default_factory=StoreListingMetadata)
    privacy: StorePrivacyMetadata = Field(default_factory=StorePrivacyMetadata)
    review: StoreReviewMetadata = Field(default_factory=StoreReviewMetadata)
    assets: StoreAssetMetadata = Field(default_factory=StoreAssetMetadata)
    commerce: StoreCommerceMetadata = Field(default_factory=StoreCommerceMetadata)
    operator_notes: list[str] = Field(default_factory=list)


class StoreChecklistItem(FrozenModel):
    item_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    status: Literal["provided", "missing", "not_applicable", "needs_review"]
    detail: str = Field(min_length=1)
    source_urls: list[str] = Field(default_factory=list)


class StorePlatformSection(FrozenModel):
    platform: Literal["apple_app_store", "google_play"]
    checklist: list[StoreChecklistItem] = Field(min_length=1)
    blockers: list[str]
    notes: list[str] = Field(min_length=1)


class StorePack(FrozenModel):
    run_id: str = Field(min_length=1)
    schema_version: Literal["store_pack.v1"]
    metadata_schema_version: str = Field(min_length=1)
    status: Literal["blocked", "metadata_complete_needs_submission_approval"]
    app_root: str = Field(min_length=1)
    app_type: Literal["web", "mobile", "cli", "api", "mixed"]
    official_source_urls: list[str] = Field(min_length=1)
    source_refresh_date: str = Field(pattern=DATE_PATTERN)
    platform_sections: list[StorePlatformSection] = Field(min_length=1)
    blockers: list[str]
    forbidden_without_approval: list[str] = Field(min_length=1)
    next_required_action: str = Field(min_length=1)
    disclaimer: str = Field(min_length=1)


class SupervisorDecision(FrozenModel):
    status: Literal["continue", "request_more_research", "kill"]
    reason: str = Field(min_length=1)
    signal_count: int = Field(ge=0)
    high_or_medium_relevance_count: int = Field(ge=0)
    required_next_artifact: str | None = None


@unique
class RuntimeMode(StrEnum):
    LOCAL_CODEX_DESKTOP = "local_codex_desktop"


class RuntimePolicy(FrozenModel):
    mode: RuntimeMode
    operator: str = Field(min_length=1)
    server_required: bool
    frontend_required: bool
    llm_api_required: bool


class WorkflowStage(FrozenModel):
    name: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    primary_artifact: str = Field(min_length=1)
    requires_llm_api: bool


class DeployTarget(FrozenModel):
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    required_for_orchestrator: bool
    human_approval_required: bool


class HumanApprovalGate(FrozenModel):
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class Signal2ShipRunManifest(FrozenModel):
    topic: str = Field(min_length=1)
    runtime: RuntimePolicy
    stages: list[WorkflowStage]
    deploy_target: DeployTarget
    human_approval_gates: list[HumanApprovalGate]
    max_revisions_per_stage: int = Field(ge=0)


class OpportunityScore(FrozenModel):
    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    target_user: str = Field(min_length=1)
    pain_point: str = Field(min_length=1)
    evidence_signal_ids: list[str]
    score: int = Field(ge=0, le=100)
    recommendation: Literal[
        "continue_with_top_idea",
        "request_more_research",
        "kill_run",
    ]


class Signal2ShipWorkflowResult(FrozenModel):
    status: Literal[
        "app_generated",
        "needs_spec_approval",
        "needs_deploy_approval",
        "needs_store_metadata",
        "needs_store_submission_approval",
        "preview_ready",
        "request_more_research",
        "verified",
        "kill_run",
    ]
    selected_opportunity: str | None
    artifacts: list[str]
    output_dir: str
    app_dir: str | None
    reason: str = Field(min_length=1)
    run_id: str | None = None
    run_state: RunState | None = None
    approval_packet: str | None = None
    approval_packet_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    app_contract: str | None = None
    verification_record: str | None = None
    policy_review: str | None = None
    deployment_bundle: str | None = None
    store_pack: str | None = None
