from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from signal2ship.cli import app
from signal2ship.models import SupervisorDecision
from tests.fixtures import JsonValue, make_ledger, make_signal


def test_cli_outputs_continue_decision(tmp_path: Path) -> None:
    # Given
    runner = CliRunner()
    ledger = _write_json(tmp_path / "evidence_ledger.json", make_ledger(15))

    # When
    result = runner.invoke(app, [str(ledger)])

    # Then
    assert result.exit_code == 0
    decision = SupervisorDecision.model_validate_json(result.stdout)
    assert decision.status == "continue"
    assert decision.required_next_artifact == "outputs/ideas/scored_ideas.md"


def test_cli_rejects_malformed_ledger(tmp_path: Path) -> None:
    # Given
    runner = CliRunner()
    signal = make_signal(index=0)
    del signal["url"]
    ledger = _write_json(
        tmp_path / "evidence_ledger.malformed.json",
        {
            "domain": "AI coding agent workflow",
            "generated_at": "2026-06-08",
            "signals": [signal],
        },
    )

    # When
    result = runner.invoke(app, [str(ledger)])

    # Then
    assert result.exit_code == 1
    assert "url" in result.output
    assert "Traceback" not in result.output


def test_cli_outputs_request_more_research_decision(tmp_path: Path) -> None:
    # Given
    runner = CliRunner()
    ledger = _write_json(tmp_path / "evidence_ledger.thin.json", make_ledger(4))

    # When
    result = runner.invoke(app, [str(ledger)])

    # Then
    assert result.exit_code == 0
    decision = SupervisorDecision.model_validate_json(result.stdout)
    assert decision.status == "request_more_research"
    assert decision.required_next_artifact == "outputs/signals/evidence_ledger.json"


def test_cli_hides_pretty_exception_locals() -> None:
    assert app.pretty_exceptions_show_locals is False


def _write_json(path: Path, payload: dict[str, JsonValue]) -> Path:
    _ = path.write_text(json.dumps(payload), encoding="utf-8")
    return path
