from __future__ import annotations

from signal2ship.models import RuntimeMode
from signal2ship.runtime import build_local_run_manifest


def test_build_local_run_manifest_uses_codex_desktop_when_topic_is_given() -> None:
    # Given
    topic = "AI coding agent workflow pain"

    # When
    manifest = build_local_run_manifest(topic)

    # Then
    assert manifest.topic == topic
    assert manifest.runtime.mode is RuntimeMode.LOCAL_CODEX_DESKTOP
    assert manifest.runtime.server_required is False
    assert manifest.runtime.frontend_required is False
    assert manifest.deploy_target.name == "oci_preview_optional"


def test_build_local_run_manifest_blocks_production_actions_without_approval() -> None:
    # Given
    topic = "AI coding agent workflow pain"

    # When
    manifest = build_local_run_manifest(topic)

    # Then
    blocked = {gate.action for gate in manifest.human_approval_gates}
    assert blocked == {
        "production_deployment",
        "payments",
        "public_launch_posts",
        "real_user_data_collection",
    }


def test_build_local_run_manifest_orders_agent_stages() -> None:
    # Given
    topic = "AI coding agent workflow pain"

    # When
    manifest = build_local_run_manifest(topic)

    # Then
    assert [stage.name for stage in manifest.stages] == [
        "research",
        "opportunity_scoring",
        "product_scope",
        "app_build",
        "qa_release_review",
        "preview_deploy_bundle",
    ]
    assert manifest.stages[0].primary_artifact == "outputs/signals/evidence_ledger.json"
