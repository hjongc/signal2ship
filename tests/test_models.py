from __future__ import annotations

import pytest
from pydantic import ValidationError

from signal2ship.models import EvidenceLedger, IdeaSpecApprovalPacket, RunState
from tests.fixtures import make_ledger, make_signal


def test_evidence_ledger_accepts_valid_signal() -> None:
    # Given
    payload = make_ledger(signal_count=1)

    # When
    ledger = EvidenceLedger.model_validate(payload)

    # Then
    assert ledger.signals[0].signal_id == "sig_000"


def test_evidence_ledger_rejects_missing_source_url() -> None:
    # Given
    signal = make_signal(index=0)
    del signal["url"]
    payload = {
        "domain": "AI coding agent workflow",
        "generated_at": "2026-06-08",
        "signals": [signal],
    }

    # When / Then
    with pytest.raises(ValidationError, match="url"):
        _ = EvidenceLedger.model_validate(payload)


def test_idea_spec_approval_packet_requires_approval_fields() -> None:
    # Given
    payload = {
        "run_id": "run_001",
        "state": RunState.NEEDS_SPEC_APPROVAL,
        "topic": "AI coding agent workflow pain",
        "idea": "Recurring Agent Workflow Control",
        "opportunity_score": 84,
        "target_user": "developers using Codex CLI",
        "core_problem": "Recurring agent workflows are hard to control.",
        "mvp_scope": ["Build one focused workflow gate."],
        "non_goals": ["No production deployment."],
        "risks": ["Willingness to pay still needs validation."],
        "evidence_basis": ["sig_000: repeated workflow-control pain."],
        "evidence_signal_ids": ["sig_000"],
        "policy_privacy_notes": ["No real user data before approval."],
        "generated_at": "2026-06-08",
        "approval_required": True,
        "approved_app_creation_state": RunState.CREATING_APP,
    }
    del payload["policy_privacy_notes"]

    # When / Then
    with pytest.raises(ValidationError, match="policy_privacy_notes"):
        _ = IdeaSpecApprovalPacket.model_validate(payload)
