from __future__ import annotations

from signal2ship.models import EvidenceLedger
from signal2ship.supervisor import decide_after_research
from tests.fixtures import make_ledger


def test_supervisor_continues_when_evidence_gate_passes() -> None:
    # Given
    ledger = EvidenceLedger.model_validate(make_ledger(signal_count=15))

    # When
    decision = decide_after_research(ledger)

    # Then
    assert decision.status == "continue"
    assert decision.required_next_artifact == "outputs/ideas/scored_ideas.md"


def test_supervisor_requests_more_research_for_thin_evidence() -> None:
    # Given
    ledger = EvidenceLedger.model_validate(make_ledger(signal_count=4))

    # When
    decision = decide_after_research(ledger)

    # Then
    assert decision.status == "request_more_research"
    assert decision.required_next_artifact == "outputs/signals/evidence_ledger.json"


def test_supervisor_kills_empty_research() -> None:
    # Given
    ledger = EvidenceLedger.model_validate(make_ledger(signal_count=0))

    # When
    decision = decide_after_research(ledger)

    # Then
    assert decision.status == "kill"
    assert decision.required_next_artifact is None
