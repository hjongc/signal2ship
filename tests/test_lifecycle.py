from __future__ import annotations

import pytest
from pydantic import ValidationError

from signal2ship.lifecycle import (
    ALLOWED_RUN_TRANSITIONS,
    ApprovalIntegrityError,
    RunLifecycleError,
    content_sha256,
    is_transition_allowed,
    require_approved_build_start,
    require_transition,
)
from signal2ship.models import ApprovalPacket, RunState

APPROVED_SPEC = "# MVP Spec\n\nBuild the approved personal app factory slice.\n"


def test_run_lifecycle_allows_only_explicit_transitions() -> None:
    assert is_transition_allowed(
        RunState.RESEARCHING,
        RunState.NEEDS_SPEC_APPROVAL,
    )
    assert is_transition_allowed(
        RunState.RESEARCHING,
        RunState.INSUFFICIENT_EVIDENCE,
    )
    assert not is_transition_allowed(
        RunState.RESEARCHING,
        RunState.CREATING_APP,
    )


def test_all_run_states_are_registered_in_transition_map() -> None:
    assert set(ALLOWED_RUN_TRANSITIONS) == set(RunState)


def test_store_pack_states_are_terminal_and_reachable_from_verified() -> None:
    assert is_transition_allowed(
        RunState.VERIFIED,
        RunState.NEEDS_STORE_METADATA,
    )
    assert is_transition_allowed(
        RunState.VERIFIED,
        RunState.NEEDS_STORE_SUBMISSION_APPROVAL,
    )
    assert ALLOWED_RUN_TRANSITIONS[RunState.NEEDS_STORE_METADATA] == frozenset()
    assert (
        ALLOWED_RUN_TRANSITIONS[RunState.NEEDS_STORE_SUBMISSION_APPROVAL]
        == frozenset()
    )


def test_require_transition_rejects_build_before_spec_approval() -> None:
    with pytest.raises(RunLifecycleError, match="needs_spec_approval"):
        require_transition(RunState.NEEDS_SPEC_APPROVAL, RunState.CREATING_APP)


def test_approval_packet_requires_integrity_fields() -> None:
    payload = _approval_packet_payload()
    del payload["run_id"]

    with pytest.raises(ValidationError, match="run_id"):
        _ = ApprovalPacket.model_validate(payload)


def test_require_approved_build_start_accepts_matching_packet() -> None:
    approval = _approval_packet()

    require_approved_build_start(
        current_state=RunState.SPEC_APPROVED,
        approval=approval,
        run_id="run_001",
        approved_artifact_content=APPROVED_SPEC,
    )


def test_require_approved_build_start_rejects_unapproved_state() -> None:
    approval = _approval_packet()

    with pytest.raises(ApprovalIntegrityError, match="spec_approved"):
        require_approved_build_start(
            current_state=RunState.NEEDS_SPEC_APPROVAL,
            approval=approval,
            run_id="run_001",
            approved_artifact_content=APPROVED_SPEC,
        )


def test_require_approved_build_start_rejects_hash_mismatch() -> None:
    approval = _approval_packet()

    with pytest.raises(ApprovalIntegrityError, match="content hash"):
        require_approved_build_start(
            current_state=RunState.SPEC_APPROVED,
            approval=approval,
            run_id="run_001",
            approved_artifact_content=f"{APPROVED_SPEC}\nEdited after approval.",
        )


def test_require_approved_build_start_rejects_wrong_run_id() -> None:
    approval = _approval_packet()

    with pytest.raises(ApprovalIntegrityError, match="run_id"):
        require_approved_build_start(
            current_state=RunState.SPEC_APPROVED,
            approval=approval,
            run_id="run_002",
            approved_artifact_content=APPROVED_SPEC,
        )


def test_require_approved_build_start_rejects_invalid_next_state() -> None:
    approval = _approval_packet(allowed_next_state=RunState.VERIFIED)

    with pytest.raises(RunLifecycleError, match="verified"):
        require_approved_build_start(
            current_state=RunState.SPEC_APPROVED,
            approval=approval,
            run_id="run_001",
            approved_artifact_content=APPROVED_SPEC,
        )


def _approval_packet(
    *,
    allowed_next_state: RunState = RunState.CREATING_APP,
) -> ApprovalPacket:
    return ApprovalPacket.model_validate(
        _approval_packet_payload(allowed_next_state=allowed_next_state),
    )


def _approval_packet_payload(
    *,
    allowed_next_state: RunState = RunState.CREATING_APP,
) -> dict[str, str | RunState]:
    return {
        "run_id": "run_001",
        "artifact_path": "outputs/product/MVP_SPEC.md",
        "content_hash": content_sha256(APPROVED_SPEC),
        "artifact_version": "approval_packet.v1",
        "operator": "codex",
        "approved_at": "2026-06-09T10:00:00+09:00",
        "allowed_next_state": allowed_next_state,
        "approval_reason": "Approved narrow MVP scope.",
    }
