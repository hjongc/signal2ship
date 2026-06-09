from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import EvidenceLedger, IdeaSpecApprovalPacket, OpportunityScore


def render_scored_ideas(
    topic: str,
    opportunity: OpportunityScore,
    ledger: EvidenceLedger,
    llm_note: str,
) -> str:
    lines = [
        "# Scored Ideas",
        "",
        f"Topic: {topic}",
        "",
        f"## 1. {opportunity.title}",
        "",
        f"- Slug: `{opportunity.slug}`",
        f"- Target user: {opportunity.target_user}",
        f"- Pain point: {opportunity.pain_point}",
        f"- Score: {opportunity.score}/100",
        f"- Evidence count: {len(ledger.signals)} signals",
        "- Recommendation: continue_with_top_idea",
        "",
    ]
    return _append_llm_note(lines, llm_note)


def render_mvp_spec(
    topic: str,
    opportunity: OpportunityScore,
    ledger: EvidenceLedger,
    llm_note: str,
) -> str:
    lines = [
        "# MVP Spec",
        "",
        f"Topic: {topic}",
        f"Product: {opportunity.title}",
        f"Target user: {opportunity.target_user}",
        f"Core problem: {opportunity.pain_point}",
        "",
        "## Non-goals",
        "",
        "- No production deployment without human approval.",
        "- No payments.",
        "- No real user data collection.",
        "",
        "## User Flow",
        "",
        "1. Review the evidence-backed workflow pain.",
        "2. Select a small agent workflow to control.",
        "3. Follow the checklist and approval gates.",
        "",
        "## Features",
        "",
        "- Evidence summary.",
        "- Workflow checklist.",
        "- Human approval gates.",
        "",
        "## Acceptance Criteria",
        "",
        f"- Shows {len(ledger.signals)} source-backed signals.",
        "- Makes production-risk actions visibly approval gated.",
        "- Can be served as a static preview app.",
        "",
    ]
    return _append_llm_note(lines, llm_note)


def render_idea_spec_approval_packet(
    packet: IdeaSpecApprovalPacket,
    product_note: str,
) -> str:
    lines = [
        "# Idea / MVP Spec Approval Packet",
        "",
        f"Run ID: `{packet.run_id}`",
        f"State: `{packet.state.value}`",
        f"Topic: {packet.topic}",
        f"Idea: {packet.idea}",
        f"Target user: {packet.target_user}",
        f"Core problem: {packet.core_problem}",
        f"Generated at: {packet.generated_at}",
        "",
        "## MVP Scope",
        "",
        *[f"- {item}" for item in packet.mvp_scope],
        "",
        "## Non-goals",
        "",
        *[f"- {item}" for item in packet.non_goals],
        "",
        "## Risks",
        "",
        *[f"- {item}" for item in packet.risks],
        "",
        "## Evidence Basis",
        "",
        *[f"- {item}" for item in packet.evidence_basis],
        "",
        "## Evidence Signal IDs",
        "",
        *[f"- `{signal_id}`" for signal_id in packet.evidence_signal_ids],
        "",
        "## Policy / Privacy Notes",
        "",
        *[f"- {item}" for item in packet.policy_privacy_notes],
        "",
        "## Approval Gate",
        "",
        "- App creation is blocked until this packet is explicitly approved.",
        (
            "- The approval record must point to this packet and allow "
            f"`{packet.approved_app_creation_state.value}`."
        ),
        "- If this packet changes after approval, app creation must fail.",
        "",
    ]
    return _append_llm_note(lines, product_note)


def _append_llm_note(lines: list[str], llm_note: str) -> str:
    if llm_note.strip() != "":
        lines.extend(["## LLM Stage Note", "", llm_note.strip(), ""])
    return "\n".join(lines)
