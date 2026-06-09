from __future__ import annotations

from .evidence import count_relevant_signals, has_enough_evidence
from .models import EvidenceLedger, SupervisorDecision


def decide_after_research(ledger: EvidenceLedger) -> SupervisorDecision:
    relevant_count = count_relevant_signals(ledger)

    if has_enough_evidence(ledger):
        return SupervisorDecision(
            status="continue",
            reason="Evidence gate passed. Proceed to opportunity scoring.",
            signal_count=len(ledger.signals),
            high_or_medium_relevance_count=relevant_count,
            required_next_artifact="outputs/ideas/scored_ideas.md",
        )

    if len(ledger.signals) == 0:
        return SupervisorDecision(
            status="kill",
            reason=(
                "No evidence was collected. Stop instead of inventing a product idea."
            ),
            signal_count=0,
            high_or_medium_relevance_count=0,
        )

    return SupervisorDecision(
        status="request_more_research",
        reason="Evidence is not strong enough for opportunity scoring.",
        signal_count=len(ledger.signals),
        high_or_medium_relevance_count=relevant_count,
        required_next_artifact="outputs/signals/evidence_ledger.json",
    )
