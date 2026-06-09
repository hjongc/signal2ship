from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from signal2ship.cli import app
from signal2ship.models import EvidenceLedger
from tests.fixtures import SOURCE_URL_BASE, make_last30days_markdown

if TYPE_CHECKING:
    import pytest


def test_research_cli_writes_evidence_ledger_from_raw_research(
    tmp_path: Path,
) -> None:
    # Given
    runner = CliRunner()
    raw_file = tmp_path / "last30days.md"
    output = tmp_path / "evidence_ledger.json"
    _ = raw_file.write_text(make_last30days_markdown(), encoding="utf-8")

    # When
    result = runner.invoke(
        app,
        [
            "research",
            "AI coding agent workflow pain",
            "--raw-file",
            str(raw_file),
            "--output",
            str(output),
        ],
    )

    # Then
    assert result.exit_code == 0
    assert "completed research ledger generation" in result.output
    ledger = EvidenceLedger.model_validate_json(output.read_text(encoding="utf-8"))
    assert len(ledger.signals) >= 15
    assert str(ledger.signals[0].url) == f"{SOURCE_URL_BASE}/1"


def test_research_cli_rejects_malformed_last30days_research(tmp_path: Path) -> None:
    # Given
    runner = CliRunner()
    raw_file = tmp_path / "last30days.malformed.md"
    output = tmp_path / "evidence_ledger.malformed.json"
    _ = raw_file.write_text(
        make_last30days_markdown(signal_count=1, include_url=False),
        encoding="utf-8",
    )

    # When
    result = runner.invoke(
        app,
        [
            "research",
            "AI coding agent workflow pain",
            "--raw-file",
            str(raw_file),
            "--output",
            str(output),
        ],
    )

    # Then
    assert result.exit_code == 1
    assert "research input error" in result.output
    assert "URL" in result.output
    assert "Traceback" not in result.output
    assert not output.exists()


def test_research_cli_reports_missing_last30days_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    runner = CliRunner()
    output = tmp_path / "evidence_ledger.json"
    missing_skill_dir = tmp_path / "missing-last30days"
    monkeypatch.setenv("SIGNAL2SHIP_LAST30DAYS_SKILL_DIR", str(missing_skill_dir))

    # When
    result = runner.invoke(
        app,
        [
            "research",
            "AI coding agent workflow pain",
            "--use-last30days",
            "--output",
            str(output),
        ],
    )

    # Then
    assert result.exit_code == 1
    assert "last30days unavailable" in result.output
    assert "npx skills add mvanhorn/last30days-skill -g" in result.output
    assert "Traceback" not in result.output
    assert not output.exists()
