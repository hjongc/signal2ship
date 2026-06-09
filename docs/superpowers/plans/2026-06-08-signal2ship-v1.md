# Signal2Ship v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first executable Signal2Ship slice: goal intake, market research task creation, evidence ledger validation, and supervisor kill-or-continue decision.

**Architecture:** Start with a local CLI orchestrator that reads a goal and domain, creates a structured Market Research task, accepts or imports research artifacts, validates the evidence ledger, and writes a supervisor decision. Do not build app generation until the evidence gate works.

**Tech Stack:** Python 3.12+, Pydantic v2 for typed artifacts, pytest for validation tests, Markdown and JSON artifact files.

---

## File Structure

- Create `src/signal2ship/models.py` for typed task, result, evidence, and decision models.
- Create `src/signal2ship/evidence.py` for evidence ledger loading and validation.
- Create `src/signal2ship/supervisor.py` for kill-or-continue logic.
- Create `src/signal2ship/cli.py` for the local command entry point.
- Create `tests/test_evidence.py` for evidence validation.
- Create `tests/test_supervisor.py` for gate decisions.
- Modify `pyproject.toml` to define dependencies, test config, and CLI script.

### Task 1: Project Package And Models

**Files:**
- Create: `pyproject.toml`
- Create: `src/signal2ship/__init__.py`
- Create: `src/signal2ship/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Add package config**

Create `pyproject.toml`:

```toml
[project]
name = "signal2ship"
version = "0.1.0"
description = "Turn recent market signals into shippable app MVPs."
requires-python = ">=3.12"
dependencies = [
  "pydantic>=2.7,<3",
]

[project.optional-dependencies]
dev = [
  "pytest>=8,<9",
]

[project.scripts]
signal2ship = "signal2ship.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Create typed artifact models**

Create `src/signal2ship/models.py`:

```python
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BusinessRelevance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Engagement(BaseModel):
    upvotes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    views: int | None = Field(default=None, ge=0)


class EvidenceSignal(BaseModel):
    signal_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    url: HttpUrl
    observed_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    audience: str = Field(min_length=1)
    pain_point: str = Field(min_length=1)
    evidence_summary: str = Field(min_length=1)
    engagement: Engagement = Field(default_factory=Engagement)
    business_relevance: BusinessRelevance
    confidence: Confidence
    validation_needed: str = Field(min_length=1)


class EvidenceLedger(BaseModel):
    domain: str = Field(min_length=1)
    generated_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    signals: list[EvidenceSignal]


class SupervisorDecision(BaseModel):
    status: Literal["continue", "request_more_research", "kill"]
    reason: str = Field(min_length=1)
    signal_count: int = Field(ge=0)
    high_or_medium_relevance_count: int = Field(ge=0)
    required_next_artifact: str | None = None
```

- [ ] **Step 3: Add model tests**

Create `tests/test_models.py`:

```python
from pydantic import ValidationError
import pytest

from signal2ship.models import EvidenceLedger


def test_evidence_ledger_accepts_valid_signal() -> None:
    ledger = EvidenceLedger.model_validate(
        {
            "domain": "AI coding agent workflow",
            "generated_at": "2026-06-08",
            "signals": [
                {
                    "signal_id": "sig_001",
                    "source": "reddit",
                    "url": "https://github.com/openai/codex/issues/1",
                    "observed_at": "2026-06-08",
                    "audience": "developers",
                    "pain_point": "Recurring workflows are hard to control.",
                    "evidence_summary": "Users describe manual prompt copying.",
                    "engagement": {"upvotes": 100, "comments": 20},
                    "business_relevance": "medium",
                    "confidence": "medium",
                    "validation_needed": "Interview target users.",
                }
            ],
        }
    )

    assert ledger.signals[0].signal_id == "sig_001"


def test_evidence_ledger_rejects_missing_source_url() -> None:
    with pytest.raises(ValidationError):
        EvidenceLedger.model_validate(
            {
                "domain": "AI coding agent workflow",
                "generated_at": "2026-06-08",
                "signals": [
                    {
                        "signal_id": "sig_001",
                        "source": "reddit",
                        "observed_at": "2026-06-08",
                        "audience": "developers",
                        "pain_point": "Recurring workflows are hard to control.",
                        "evidence_summary": "Users describe manual prompt copying.",
                        "business_relevance": "medium",
                        "confidence": "medium",
                        "validation_needed": "Interview target users.",
                    }
                ],
            }
        )
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_models.py -q`

Expected: tests pass after dependencies are installed.

### Task 2: Evidence Gate

**Files:**
- Create: `src/signal2ship/evidence.py`
- Test: `tests/test_evidence.py`

- [ ] **Step 1: Implement evidence validation**

Create `src/signal2ship/evidence.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from signal2ship.models import BusinessRelevance, EvidenceLedger


MINIMUM_SIGNALS = 15


def load_ledger(path: Path) -> EvidenceLedger:
    return EvidenceLedger.model_validate(json.loads(path.read_text()))


def count_relevant_signals(ledger: EvidenceLedger) -> int:
    return sum(
        1
        for signal in ledger.signals
        if signal.business_relevance
        in {BusinessRelevance.MEDIUM, BusinessRelevance.HIGH}
    )


def has_enough_evidence(ledger: EvidenceLedger) -> bool:
    return len(ledger.signals) >= MINIMUM_SIGNALS and count_relevant_signals(ledger) >= 8
```

- [ ] **Step 2: Add evidence tests**

Create `tests/test_evidence.py`:

```python
from signal2ship.evidence import count_relevant_signals, has_enough_evidence
from signal2ship.models import EvidenceLedger


def make_signal(index: int, relevance: str = "medium") -> dict[str, object]:
    return {
        "signal_id": f"sig_{index:03d}",
        "source": "reddit",
        "url": f"https://github.com/openai/codex/issues/{index + 1}",
        "observed_at": "2026-06-08",
        "audience": "developers",
        "pain_point": "Recurring workflows are hard to control.",
        "evidence_summary": "Users describe manual prompt copying.",
        "engagement": {"upvotes": 100, "comments": 20},
        "business_relevance": relevance,
        "confidence": "medium",
        "validation_needed": "Interview target users.",
    }


def test_has_enough_evidence_requires_minimum_signal_count() -> None:
    ledger = EvidenceLedger.model_validate(
        {
            "domain": "AI coding agent workflow",
            "generated_at": "2026-06-08",
            "signals": [make_signal(index) for index in range(14)],
        }
    )

    assert not has_enough_evidence(ledger)


def test_has_enough_evidence_requires_relevant_signals() -> None:
    ledger = EvidenceLedger.model_validate(
        {
            "domain": "AI coding agent workflow",
            "generated_at": "2026-06-08",
            "signals": [make_signal(index, "low") for index in range(15)],
        }
    )

    assert count_relevant_signals(ledger) == 0
    assert not has_enough_evidence(ledger)


def test_has_enough_evidence_passes_when_gate_is_met() -> None:
    ledger = EvidenceLedger.model_validate(
        {
            "domain": "AI coding agent workflow",
            "generated_at": "2026-06-08",
            "signals": [make_signal(index) for index in range(15)],
        }
    )

    assert count_relevant_signals(ledger) == 15
    assert has_enough_evidence(ledger)
```

- [ ] **Step 3: Run evidence tests**

Run: `python3 -m pytest tests/test_evidence.py -q`

Expected: all tests pass.

### Task 3: Supervisor Decision

**Files:**
- Create: `src/signal2ship/supervisor.py`
- Test: `tests/test_supervisor.py`

- [ ] **Step 1: Implement supervisor gate decision**

Create `src/signal2ship/supervisor.py`:

```python
from __future__ import annotations

from signal2ship.evidence import count_relevant_signals, has_enough_evidence
from signal2ship.models import EvidenceLedger, SupervisorDecision


def decide_after_research(ledger: EvidenceLedger) -> SupervisorDecision:
    relevant_count = count_relevant_signals(ledger)

    if has_enough_evidence(ledger):
        return SupervisorDecision(
            status="continue",
            reason="Evidence gate passed. Proceed to opportunity scoring.",
            signal_count=len(ledger.signals),
            high_or_medium_relevance_count=relevant_count,
            required_next_artifact="outputs/ideas/scored_ideas.md",
        )

    if len(ledger.signals) == 0:
        return SupervisorDecision(
            status="kill",
            reason="No evidence was collected. Stop instead of inventing a product idea.",
            signal_count=0,
            high_or_medium_relevance_count=0,
        )

    return SupervisorDecision(
        status="request_more_research",
        reason="Evidence is not strong enough for opportunity scoring.",
        signal_count=len(ledger.signals),
        high_or_medium_relevance_count=relevant_count,
        required_next_artifact="outputs/signals/evidence_ledger.json",
    )
```

- [ ] **Step 2: Add supervisor tests**

Create `tests/test_supervisor.py`:

```python
from signal2ship.models import EvidenceLedger
from signal2ship.supervisor import decide_after_research


def make_signal(index: int, relevance: str = "medium") -> dict[str, object]:
    return {
        "signal_id": f"sig_{index:03d}",
        "source": "reddit",
        "url": f"https://github.com/openai/codex/issues/{index + 1}",
        "observed_at": "2026-06-08",
        "audience": "developers",
        "pain_point": "Recurring workflows are hard to control.",
        "evidence_summary": "Users describe manual prompt copying.",
        "engagement": {"upvotes": 100, "comments": 20},
        "business_relevance": relevance,
        "confidence": "medium",
        "validation_needed": "Interview target users.",
    }


def test_supervisor_continues_when_evidence_gate_passes() -> None:
    ledger = EvidenceLedger.model_validate(
        {
            "domain": "AI coding agent workflow",
            "generated_at": "2026-06-08",
            "signals": [make_signal(index) for index in range(15)],
        }
    )

    decision = decide_after_research(ledger)

    assert decision.status == "continue"
    assert decision.required_next_artifact == "outputs/ideas/scored_ideas.md"


def test_supervisor_requests_more_research_for_thin_evidence() -> None:
    ledger = EvidenceLedger.model_validate(
        {
            "domain": "AI coding agent workflow",
            "generated_at": "2026-06-08",
            "signals": [make_signal(index) for index in range(4)],
        }
    )

    decision = decide_after_research(ledger)

    assert decision.status == "request_more_research"


def test_supervisor_kills_empty_research() -> None:
    ledger = EvidenceLedger.model_validate(
        {
            "domain": "AI coding agent workflow",
            "generated_at": "2026-06-08",
            "signals": [],
        }
    )

    decision = decide_after_research(ledger)

    assert decision.status == "kill"
```

- [ ] **Step 3: Run supervisor tests**

Run: `python3 -m pytest tests/test_supervisor.py -q`

Expected: all tests pass.

### Task 4: CLI Slice

**Files:**
- Create: `src/signal2ship/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Implement CLI decision command**

Create `src/signal2ship/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from signal2ship.evidence import load_ledger
from signal2ship.supervisor import decide_after_research


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="signal2ship")
    parser.add_argument(
        "ledger",
        type=Path,
        help="Path to outputs/signals/evidence_ledger.json",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    ledger = load_ledger(args.ledger)
    decision = decide_after_research(ledger)
    print(json.dumps(decision.model_dump(), indent=2))
```

- [ ] **Step 2: Add CLI smoke test**

Create `tests/test_cli.py`:

```python
import json
from pathlib import Path
from subprocess import run


def test_cli_outputs_continue_decision(tmp_path: Path) -> None:
    ledger_path = tmp_path / "evidence_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "domain": "AI coding agent workflow",
                "generated_at": "2026-06-08",
                "signals": [
                    {
                        "signal_id": f"sig_{index:03d}",
                        "source": "reddit",
                        "url": f"https://github.com/openai/codex/issues/{index + 1}",
                        "observed_at": "2026-06-08",
                        "audience": "developers",
                        "pain_point": "Recurring workflows are hard to control.",
                        "evidence_summary": "Users describe manual prompt copying.",
                        "engagement": {"upvotes": 100, "comments": 20},
                        "business_relevance": "medium",
                        "confidence": "medium",
                        "validation_needed": "Interview target users.",
                    }
                    for index in range(15)
                ],
            }
        )
    )

    result = run(
        ["python3", "-m", "signal2ship.cli", str(ledger_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout)["status"] == "continue"
```

- [ ] **Step 3: Run full tests**

Run: `python3 -m pytest -q`

Expected: all tests pass.

## Self-Review

- Spec coverage: this plan covers the first executable slice only. It intentionally does not build app generation, Vercel deployment, payments, or public launch.
- Placeholder scan: no placeholder tasks are included.
- Type consistency: model names and field names are consistent across tasks.

## Execution Choice

After this plan is approved, execute it inline or with subagents. The recommended first pass is inline execution because the scope is small and the changed files are tightly coupled.
