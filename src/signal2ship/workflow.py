from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final, override

from .lifecycle import content_sha256
from .llm import LLMClient, OpenRouterModelTier
from .models import (
    EvidenceLedger,
    IdeaSpecApprovalPacket,
    OpportunityScore,
    RunState,
    Signal2ShipWorkflowResult,
)
from .rendering import (
    render_idea_spec_approval_packet,
    render_mvp_spec,
    render_scored_ideas,
)
from .research import load_research_ledger, write_ledger
from .supervisor import decide_after_research

SLUG_PATTERN: Final = re.compile(r"[^a-z0-9]+")
MAX_EVIDENCE_IDS: Final = 15
MAX_OPPORTUNITY_SCORE: Final = 100
BASE_OPPORTUNITY_SCORE: Final = 40
SCORE_PER_SIGNAL: Final = 4
RUN_ID_PREFIX: Final = "run_"


type LLMClientFactory = Callable[[], LLMClient]


@dataclass(frozen=True, slots=True)
class WorkflowDependencyError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"workflow dependency error: {self.detail}"


@dataclass(frozen=True, slots=True)
class SpecApprovalContext:
    topic: str
    ledger: EvidenceLedger
    output_dir: Path
    app_dir: Path
    ledger_path: Path
    llm_client: LLMClient


def run_local_workflow(
    *,
    topic: str,
    raw_file: Path,
    output_dir: Path,
    app_dir: Path,
    llm_client: LLMClient,
) -> Signal2ShipWorkflowResult:
    return _execute_workflow(
        topic=topic,
        raw_file=raw_file,
        output_dir=output_dir,
        app_dir=app_dir,
        llm_client_factory=lambda: llm_client,
    )


def execute_local_workflow(
    *,
    topic: str,
    raw_file: Path,
    output_dir: Path,
    app_dir: Path,
    llm_client_factory: LLMClientFactory,
) -> Signal2ShipWorkflowResult:
    return _execute_workflow(
        topic=topic,
        raw_file=raw_file,
        output_dir=output_dir,
        app_dir=app_dir,
        llm_client_factory=llm_client_factory,
    )


def _execute_workflow(
    *,
    topic: str,
    raw_file: Path,
    output_dir: Path,
    app_dir: Path,
    llm_client_factory: LLMClientFactory,
) -> Signal2ShipWorkflowResult:
    ledger = load_research_ledger(raw_file, topic)
    ledger_path = output_dir / "signals" / "evidence_ledger.json"
    write_ledger(ledger, ledger_path)

    decision = decide_after_research(ledger)
    match decision.status:
        case "continue":
            return _build_spec_approval_workflow(
                SpecApprovalContext(
                    topic=topic,
                    ledger=ledger,
                    output_dir=output_dir,
                    app_dir=app_dir,
                    ledger_path=ledger_path,
                    llm_client=llm_client_factory(),
                ),
            )
        case "request_more_research":
            return Signal2ShipWorkflowResult(
                status="request_more_research",
                selected_opportunity=None,
                artifacts=[str(ledger_path)],
                output_dir=str(output_dir),
                app_dir=None,
                reason=decision.reason,
            )
        case "kill":
            return Signal2ShipWorkflowResult(
                status="kill_run",
                selected_opportunity=None,
                artifacts=[str(ledger_path)],
                output_dir=str(output_dir),
                app_dir=None,
                reason=decision.reason,
            )


def _build_spec_approval_workflow(
    context: SpecApprovalContext,
) -> Signal2ShipWorkflowResult:
    opportunity = _score_opportunity(context.ledger)
    opportunity_note = _complete_stage(
        context.llm_client,
        system_prompt="You are the Opportunity Analyst Agent for Signal2Ship.",
        user_prompt=(
            f"Topic: {context.topic}\n"
            f"Evidence signals: {len(context.ledger.signals)}\n"
            f"Candidate opportunity: {opportunity.title}\n"
            "Give concise stage guidance grounded in the evidence."
        ),
        model_tier="pro",
    )
    product_note = _complete_stage(
        context.llm_client,
        system_prompt="You are the Product Scope Agent for Signal2Ship.",
        user_prompt=(
            f"Topic: {context.topic}\n"
            f"Selected opportunity: {opportunity.title}\n"
            "Give concise MVP scope guidance with non-goals."
        ),
    )
    run_id = _derive_run_id(context.topic, context.ledger)
    approval_packet = _build_idea_spec_approval_packet(
        run_id=run_id,
        topic=context.topic,
        opportunity=opportunity,
        ledger=context.ledger,
    )
    opportunity_json = context.output_dir / "ideas" / "opportunity_scores.json"
    scored_ideas = context.output_dir / "ideas" / "scored_ideas.md"
    mvp_spec = context.output_dir / "product" / "MVP_SPEC.md"
    approval_json = context.output_dir / "product" / "IDEA_SPEC_APPROVAL.json"
    approval_markdown = context.output_dir / "product" / "IDEA_SPEC_APPROVAL.md"

    _write_json_model(opportunity_json, opportunity)
    _write_text(
        scored_ideas,
        render_scored_ideas(
            context.topic, opportunity, context.ledger, opportunity_note
        ),
    )
    _write_text(
        mvp_spec,
        render_mvp_spec(context.topic, opportunity, context.ledger, product_note),
    )
    approval_json_content = approval_packet.model_dump_json(indent=2)
    _write_text(approval_json, approval_json_content)
    approval_content = render_idea_spec_approval_packet(
        approval_packet,
        product_note,
    )
    _write_text(approval_markdown, approval_content)

    artifacts = [
        context.ledger_path,
        opportunity_json,
        scored_ideas,
        mvp_spec,
        approval_json,
        approval_markdown,
    ]
    return Signal2ShipWorkflowResult(
        status="needs_spec_approval",
        selected_opportunity=opportunity.slug,
        artifacts=[str(artifact) for artifact in artifacts],
        output_dir=str(context.output_dir),
        app_dir=None,
        reason=(
            "Evidence gate passed and the final idea/MVP spec approval packet "
            "was generated. App creation is blocked until explicit approval."
        ),
        run_id=run_id,
        run_state=RunState.NEEDS_SPEC_APPROVAL,
        approval_packet=str(approval_json),
        approval_packet_hash=content_sha256(approval_json_content),
    )


def _score_opportunity(ledger: EvidenceLedger) -> OpportunityScore:
    lead_signal = ledger.signals[0]
    evidence_ids = [signal.signal_id for signal in ledger.signals[:MAX_EVIDENCE_IDS]]
    title = _title_from_pain(lead_signal.pain_point)
    return OpportunityScore(
        slug=_slugify(title),
        title=title,
        target_user=lead_signal.audience,
        pain_point=lead_signal.pain_point,
        evidence_signal_ids=evidence_ids,
        score=min(
            MAX_OPPORTUNITY_SCORE,
            BASE_OPPORTUNITY_SCORE + (len(evidence_ids) * SCORE_PER_SIGNAL),
        ),
        recommendation="continue_with_top_idea",
    )


def _title_from_pain(pain_point: str) -> str:
    normalized = " ".join(pain_point.rstrip(".").split())
    if normalized == "":
        raise WorkflowDependencyError(detail="lead signal pain point is empty")
    return normalized.title()


def _slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.lower()).strip("-")
    if slug == "":
        raise WorkflowDependencyError(detail="could not derive opportunity slug")
    return slug


def _derive_run_id(topic: str, ledger: EvidenceLedger) -> str:
    signal_ids = ",".join(signal.signal_id for signal in ledger.signals)
    payload = f"{topic}\n{ledger.domain}\n{ledger.generated_at}\n{signal_ids}"
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{RUN_ID_PREFIX}{digest}"


def _build_idea_spec_approval_packet(
    *,
    run_id: str,
    topic: str,
    opportunity: OpportunityScore,
    ledger: EvidenceLedger,
) -> IdeaSpecApprovalPacket:
    evidence_basis = [
        (
            f"{signal.signal_id}: {signal.source} signal for "
            f"{signal.audience} — {signal.evidence_summary}"
        )
        for signal in ledger.signals[:MAX_EVIDENCE_IDS]
    ]
    return IdeaSpecApprovalPacket(
        run_id=run_id,
        state=RunState.NEEDS_SPEC_APPROVAL,
        topic=topic,
        idea=opportunity.title,
        opportunity_score=opportunity.score,
        target_user=opportunity.target_user,
        core_problem=opportunity.pain_point,
        mvp_scope=[
            "Build one evidence-backed MVP slice for the selected opportunity.",
            "Expose the core workflow, checklist, and approval gates clearly.",
            "Keep the first app preview small enough for one focused build pass.",
        ],
        non_goals=[
            "No production deployment before explicit deployment approval.",
            "No payments before explicit approval.",
            "No real user data collection before explicit approval.",
        ],
        risks=[
            "Evidence may not prove willingness to pay yet.",
            "The generated MVP must stay narrow or be killed before build.",
            "Store/privacy policy obligations must be reviewed before release.",
        ],
        evidence_basis=evidence_basis,
        evidence_signal_ids=opportunity.evidence_signal_ids,
        policy_privacy_notes=[
            (
                "Assume no real user data collection for the first preview "
                "unless approved."
            ),
            (
                "If accounts, SDKs, tracking, payments, or mobile distribution "
                "enter scope, run the store policy readiness review before "
                "deployment."
            ),
            (
                "Deployment and store submission remain blocked by a separate "
                "human approval gate."
            ),
        ],
        generated_at=ledger.generated_at,
        approval_required=True,
        approved_app_creation_state=RunState.CREATING_APP,
    )


def _complete_stage(
    llm_client: LLMClient,
    *,
    system_prompt: str,
    user_prompt: str,
    model_tier: OpenRouterModelTier = "flash",
) -> str:
    note = llm_client.complete(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_tier=model_tier,
    )
    if note.strip() == "":
        raise WorkflowDependencyError(detail="LLM stage returned empty guidance")
    return note.strip()


def _write_json_model(
    path: Path,
    model: OpportunityScore | IdeaSpecApprovalPacket,
) -> None:
    _write_text(path, model.model_dump_json(indent=2))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")
