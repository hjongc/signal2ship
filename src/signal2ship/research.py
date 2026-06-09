from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, override

from pydantic import ValidationError

from .models import Engagement, EvidenceLedger, EvidenceSignal

FIELD_PATTERN: Final = re.compile(r"^(?P<key>[A-Za-z ]+): (?P<value>.+)$")
ENGAGEMENT_PATTERN: Final = re.compile(
    r"(?P<key>upvotes|comments|likes|views)=(?P<value>\d+)",
)
SIGNAL_MARKER: Final = "\n## Signal "
REQUIRED_FIELDS: Final = (
    "Source",
    "URL",
    "Observed",
    "Audience",
    "Pain",
    "Evidence",
    "Business Relevance",
    "Confidence",
    "Validation Needed",
)


@dataclass(frozen=True, slots=True)
class ResearchInputError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"research input error: {self.detail}"


def load_research_ledger(raw_path: Path, topic: str) -> EvidenceLedger:
    if not raw_path.is_file():
        raise ResearchInputError(detail=f"raw research file does not exist: {raw_path}")
    return parse_last30days_markdown(raw_path.read_text(encoding="utf-8"), topic=topic)


def parse_last30days_markdown(raw_markdown: str, *, topic: str) -> EvidenceLedger:
    generated_at = _generated_at(raw_markdown)
    signals = [_parse_signal(block) for block in _signal_blocks(raw_markdown)]
    if len(signals) == 0:
        raise ResearchInputError(detail="no source-backed Signal blocks found")
    return EvidenceLedger(domain=topic, generated_at=generated_at, signals=signals)


def write_ledger(ledger: EvidenceLedger, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(ledger.model_dump_json(indent=2), encoding="utf-8")


def _generated_at(raw_markdown: str) -> str:
    for line in raw_markdown.splitlines():
        match = FIELD_PATTERN.match(line.strip())
        if match is not None and match.group("key") == "Generated":
            return match.group("value")
    raise ResearchInputError(detail="missing Generated date")


def _signal_blocks(raw_markdown: str) -> list[str]:
    return [block.strip() for block in raw_markdown.split(SIGNAL_MARKER)[1:]]


def _parse_signal(block: str) -> EvidenceSignal:
    lines = block.splitlines()
    if len(lines) == 0 or lines[0].strip() == "":
        raise ResearchInputError(detail="encountered empty Signal block")

    signal_id = lines[0].strip()
    fields = _fields_from_lines(lines[1:], signal_id=signal_id)
    try:
        return EvidenceSignal.model_validate(
            {
                "signal_id": signal_id,
                "source": _required(fields, "Source", signal_id),
                "url": _required(fields, "URL", signal_id),
                "observed_at": _required(fields, "Observed", signal_id),
                "audience": _required(fields, "Audience", signal_id),
                "pain_point": _required(fields, "Pain", signal_id),
                "evidence_summary": _required(fields, "Evidence", signal_id),
                "engagement": _engagement(fields.get("Engagement", "")),
                "business_relevance": _required(
                    fields,
                    "Business Relevance",
                    signal_id,
                ),
                "confidence": _required(fields, "Confidence", signal_id),
                "validation_needed": _required(fields, "Validation Needed", signal_id),
            }
        )
    except ValidationError as error:
        detail = f"invalid Signal {signal_id}: {error}"
        raise ResearchInputError(detail=detail) from error


def _fields_from_lines(lines: list[str], *, signal_id: str) -> Mapping[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        match = FIELD_PATTERN.match(line.strip())
        if match is not None:
            fields[match.group("key")] = match.group("value")

    missing = [field for field in REQUIRED_FIELDS if field not in fields]
    if missing:
        raise ResearchInputError(
            detail=f"Signal {signal_id} missing required field: {missing[0]}",
        )
    return fields


def _required(fields: Mapping[str, str], key: str, signal_id: str) -> str:
    value = fields.get(key)
    if value is None or value.strip() == "":
        raise ResearchInputError(
            detail=f"Signal {signal_id} missing required field: {key}",
        )
    return value


def _engagement(raw: str) -> Engagement:
    values = {
        match.group("key"): int(match.group("value"))
        for match in ENGAGEMENT_PATTERN.finditer(raw)
    }
    return Engagement(
        upvotes=values.get("upvotes"),
        comments=values.get("comments"),
        likes=values.get("likes"),
        views=values.get("views"),
    )
