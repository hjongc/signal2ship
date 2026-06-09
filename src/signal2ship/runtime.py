from __future__ import annotations

from typing import Final

from .models import (
    DeployTarget,
    HumanApprovalGate,
    RuntimeMode,
    RuntimePolicy,
    Signal2ShipRunManifest,
    WorkflowStage,
)

MAX_REVISIONS_PER_STAGE: Final = 2


def build_local_run_manifest(topic: str) -> Signal2ShipRunManifest:
    return Signal2ShipRunManifest(
        topic=topic,
        runtime=RuntimePolicy(
            mode=RuntimeMode.LOCAL_CODEX_DESKTOP,
            operator="Codex Desktop plus local CLI",
            server_required=False,
            frontend_required=False,
            llm_api_required=True,
        ),
        stages=[
            WorkflowStage(
                name="research",
                agent="MarketResearchAgent",
                objective="Collect recent market evidence before ideas are generated.",
                primary_artifact="outputs/signals/evidence_ledger.json",
                requires_llm_api=True,
            ),
            WorkflowStage(
                name="opportunity_scoring",
                agent="OpportunityAnalystAgent",
                objective="Score one narrow opportunity from the evidence ledger.",
                primary_artifact="outputs/ideas/scored_ideas.md",
                requires_llm_api=True,
            ),
            WorkflowStage(
                name="product_scope",
                agent="ProductScopeAgent",
                objective="Reduce the selected opportunity to a buildable MVP spec.",
                primary_artifact="outputs/product/MVP_SPEC.md",
                requires_llm_api=True,
            ),
            WorkflowStage(
                name="app_build",
                agent="AppBuilderAgent",
                objective="Build only the approved MVP under apps/generated.",
                primary_artifact="apps/generated/",
                requires_llm_api=True,
            ),
            WorkflowStage(
                name="qa_release_review",
                agent="QAReleaseCriticAgent",
                objective="Block release until tests and actual app usage pass.",
                primary_artifact="outputs/reviews/QA_REVIEW.md",
                requires_llm_api=True,
            ),
            WorkflowStage(
                name="preview_deploy_bundle",
                agent="VentureSupervisorAgent",
                objective=(
                    "Prepare a deploy bundle without performing production launch."
                ),
                primary_artifact="outputs/launch/",
                requires_llm_api=False,
            ),
        ],
        deploy_target=DeployTarget(
            name="oci_preview_optional",
            purpose="Preview deployment target for generated MVP apps only.",
            required_for_orchestrator=False,
            human_approval_required=True,
        ),
        human_approval_gates=[
            HumanApprovalGate(
                action="production_deployment",
                reason=(
                    "Production launch changes public availability and infrastructure."
                ),
            ),
            HumanApprovalGate(
                action="payments",
                reason="Payment activation creates billing and compliance risk.",
            ),
            HumanApprovalGate(
                action="public_launch_posts",
                reason="Public messaging should be approved by the operator.",
            ),
            HumanApprovalGate(
                action="real_user_data_collection",
                reason=(
                    "Real user data requires explicit privacy and retention decisions."
                ),
            ),
        ],
        max_revisions_per_stage=MAX_REVISIONS_PER_STAGE,
    )
