from __future__ import annotations

from pathlib import Path
from typing import Final

from .models import BusinessRelevance, EvidenceLedger

MINIMUM_SIGNALS: Final = 15
MINIMUM_RELEVANT_SIGNALS: Final = 8


def load_ledger(path: Path) -> EvidenceLedger:
    return EvidenceLedger.model_validate_json(path.read_text(encoding="utf-8"))


def is_relevant(relevance: BusinessRelevance) -> bool:
    match relevance:
        case BusinessRelevance.HIGH | BusinessRelevance.MEDIUM:
            return True
        case BusinessRelevance.LOW:
            return False


def count_relevant_signals(ledger: EvidenceLedger) -> int:
    return sum(1 for signal in ledger.signals if is_relevant(signal.business_relevance))


def has_enough_evidence(ledger: EvidenceLedger) -> bool:
    return (
        len(ledger.signals) >= MINIMUM_SIGNALS
        and count_relevant_signals(ledger) >= MINIMUM_RELEVANT_SIGNALS
    )
