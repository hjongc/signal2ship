from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from signal2ship.workflow import run_local_workflow
from tests.fixtures import make_last30days_markdown

if TYPE_CHECKING:
    from signal2ship.llm import OpenRouterModelTier


@dataclass(slots=True)
class RecordingLLMClient:
    calls: list[tuple[str, str, OpenRouterModelTier]] = field(default_factory=list)

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_tier: OpenRouterModelTier = "flash",
    ) -> str:
        self.calls.append((system_prompt, user_prompt, model_tier))
        return "OpenRouter generated stage guidance."


def test_run_local_workflow_includes_llm_stage_notes_when_client_is_supplied(
    tmp_path: Path,
) -> None:
    # Given
    client = RecordingLLMClient()
    raw_file = tmp_path / "last30days.md"
    output_dir = tmp_path / "outputs"
    app_dir = tmp_path / "apps" / "generated"
    _ = raw_file.write_text(make_last30days_markdown(), encoding="utf-8")

    # When
    result = run_local_workflow(
        topic="AI coding agent workflow pain",
        raw_file=raw_file,
        output_dir=output_dir,
        app_dir=app_dir,
        llm_client=client,
    )

    # Then
    assert result.status == "needs_spec_approval"
    assert len(client.calls) == 2
    assert [call[2] for call in client.calls] == ["pro", "flash"]
    assert "OpenRouter generated stage guidance." in (
        output_dir / "ideas" / "scored_ideas.md"
    ).read_text(encoding="utf-8")
    assert "OpenRouter generated stage guidance." in (
        output_dir / "product" / "MVP_SPEC.md"
    ).read_text(encoding="utf-8")
    assert "OpenRouter generated stage guidance." in (
        output_dir / "product" / "IDEA_SPEC_APPROVAL.md"
    ).read_text(encoding="utf-8")
    assert not app_dir.exists()
