from __future__ import annotations

from signal2ship.evidence import count_relevant_signals, has_enough_evidence
from signal2ship.models import EvidenceLedger
from tests.fixtures import make_ledger


def test_has_enough_evidence_requires_minimum_signal_count() -> None:
    # Given
    ledger = EvidenceLedger.model_validate(make_ledger(signal_count=14))

    # When
    result = has_enough_evidence(ledger)

    # Then
    assert not result


def test_has_enough_evidence_requires_relevant_signals() -> None:
    # Given
    ledger = EvidenceLedger.model_validate(
        make_ledger(signal_count=15, relevance="low")
    )

    # When
    relevant_count = count_relevant_signals(ledger)
    result = has_enough_evidence(ledger)

    # Then
    assert relevant_count == 0
    assert not result


def test_has_enough_evidence_passes_when_gate_is_met() -> None:
    # Given
    ledger = EvidenceLedger.model_validate(make_ledger(signal_count=15))

    # When
    relevant_count = count_relevant_signals(ledger)
    result = has_enough_evidence(ledger)

    # Then
    assert relevant_count == 15
    assert result
