from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final, override

from .models import ApprovalPacket, RunState

ALLOWED_RUN_TRANSITIONS: Final[dict[RunState, frozenset[RunState]]] = {
    RunState.RESEARCHING: frozenset(
        {
            RunState.INSUFFICIENT_EVIDENCE,
            RunState.NEEDS_SPEC_APPROVAL,
        },
    ),
    RunState.INSUFFICIENT_EVIDENCE: frozenset(),
    RunState.NEEDS_SPEC_APPROVAL: frozenset({RunState.SPEC_APPROVED}),
    RunState.SPEC_APPROVED: frozenset({RunState.CREATING_APP}),
    RunState.CREATING_APP: frozenset(
        {
            RunState.VERIFICATION_FAILED,
            RunState.VERIFIED,
        },
    ),
    RunState.VERIFICATION_FAILED: frozenset(),
    RunState.VERIFIED: frozenset(
        {
            RunState.BUNDLE_READY,
            RunState.NEEDS_STORE_METADATA,
            RunState.NEEDS_STORE_SUBMISSION_APPROVAL,
        },
    ),
    RunState.BUNDLE_READY: frozenset({RunState.NEEDS_DEPLOY_APPROVAL}),
    RunState.NEEDS_DEPLOY_APPROVAL: frozenset(),
    RunState.NEEDS_STORE_METADATA: frozenset(),
    RunState.NEEDS_STORE_SUBMISSION_APPROVAL: frozenset(),
}


@dataclass(frozen=True, slots=True)
class RunLifecycleError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"run lifecycle error: {self.detail}"


@dataclass(frozen=True, slots=True)
class ApprovalIntegrityError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"approval integrity error: {self.detail}"


def content_sha256(content: bytes | str) -> str:
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


def is_transition_allowed(current_state: RunState, next_state: RunState) -> bool:
    return next_state in ALLOWED_RUN_TRANSITIONS[current_state]


def require_transition(current_state: RunState, next_state: RunState) -> None:
    if is_transition_allowed(current_state, next_state):
        return

    raise RunLifecycleError(
        detail=f"{current_state.value} cannot transition to {next_state.value}",
    )


def require_approved_build_start(
    *,
    current_state: RunState,
    approval: ApprovalPacket,
    run_id: str,
    approved_artifact_content: bytes | str,
) -> None:
    if current_state is not RunState.SPEC_APPROVED:
        raise ApprovalIntegrityError(
            detail="building requires spec_approved run state",
        )

    require_transition(current_state, approval.allowed_next_state)

    if approval.allowed_next_state is not RunState.CREATING_APP:
        raise ApprovalIntegrityError(
            detail=(
                "approval packet allowed_next_state must be creating_app "
                "before app generation"
            ),
        )

    if approval.run_id != run_id:
        raise ApprovalIntegrityError(
            detail=f"approval packet run_id {approval.run_id} does not match {run_id}",
        )

    current_hash = content_sha256(approved_artifact_content)
    if approval.content_hash != current_hash:
        raise ApprovalIntegrityError(
            detail="approved artifact content hash does not match approval packet",
        )
