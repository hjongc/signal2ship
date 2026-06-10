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
ENRICHED_SIGNAL_MARKER: Final = "\n### "
SIGNAL_MARKER: Final = "\n## Signal "
DATE_RANGE_PATTERN: Final = re.compile(r"Date range: .* to (?P<date>\d{4}-\d{2}-\d{2})")
SOURCE_HEADER_PATTERN: Final = re.compile(
    r"^###\s+\d+\.\s+(?P<title>.+?)(?:\s*\(score.*)?$",
)
NUMBERED_SOURCE_PATTERN: Final = re.compile(
    r"^\d+\.\s*\[(?P<source>[^\]]+)\] (?P<title>.+)$",
)
DATE_PREFIX_PATTERN: Final = re.compile(r"^\-\s*(?P<date>\d{4}-\d{2}-\d{2})\b")

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
    signals = [
        _parse_signal(block, topic=topic, index=idx)
        for idx, block in enumerate(_signal_blocks(raw_markdown))
    ]
    if len(signals) == 0:
        raise ResearchInputError(detail="no source-backed Signal blocks found")
    return EvidenceLedger(domain=topic, generated_at=generated_at, signals=signals)


def write_ledger(ledger: EvidenceLedger, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(ledger.model_dump_json(indent=2), encoding="utf-8")


def _generated_at(raw_markdown: str) -> str:
    date_range_match = DATE_RANGE_PATTERN.search(raw_markdown)
    if date_range_match is not None:
        return date_range_match.group("date")

    for line in raw_markdown.splitlines():
        match = FIELD_PATTERN.match(line.strip())
        if match is not None and match.group("key") == "Generated":
            return match.group("value")
    raise ResearchInputError(detail="missing Generated date")


def _signal_blocks(raw_markdown: str) -> list[str]:
    if SIGNAL_MARKER in raw_markdown:
        return [block.strip() for block in raw_markdown.split(SIGNAL_MARKER)[1:]]

    if ENRICHED_SIGNAL_MARKER not in raw_markdown:
        return []

    matches = list(re.finditer(r"(?m)^###\s+\d+\.\s+", raw_markdown))
    if not matches:
        return []

    blocks: list[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw_markdown)
        blocks.append(raw_markdown[start:end].strip())
    return blocks


def _parse_signal(block: str, *, topic: str, index: int) -> EvidenceSignal:
    lines = block.splitlines()
    if len(lines) == 0 or lines[0].strip() == "":
        raise ResearchInputError(detail="encountered empty Signal block")

    if block.lstrip().startswith("###"):
        fields = _parse_enriched_signal(lines=lines, topic=topic, index=index)
    else:
        signal_id = lines[0].strip()
        fields = _fields_from_lines(lines[1:], signal_id=signal_id)
        signal_id = lines[0].strip()
        fields = {
            "SignalID": signal_id,
            "Source": _required(fields, "Source", signal_id),
            "URL": _required(fields, "URL", signal_id),
            "Observed": _required(fields, "Observed", signal_id),
            "Audience": _required(fields, "Audience", signal_id),
            "Pain": _required(fields, "Pain", signal_id),
            "Evidence": _required(fields, "Evidence", signal_id),
            "Business Relevance": _required(fields, "Business Relevance", signal_id),
            "Confidence": _required(fields, "Confidence", signal_id),
            "Validation Needed": _required(fields, "Validation Needed", signal_id),
            "Engagement": _engagement(fields.get("Engagement", "")),
        }

    try:
        return EvidenceSignal.model_validate(
            {
                "signal_id": fields["SignalID"],
                "source": fields["Source"],
                "url": fields["URL"],
                "observed_at": fields["Observed"],
                "audience": fields["Audience"],
                "pain_point": fields["Pain"],
                "evidence_summary": fields["Evidence"],
                "engagement": fields["Engagement"],
                "business_relevance": fields["Business Relevance"],
                "confidence": fields["Confidence"],
                "validation_needed": fields["Validation Needed"],
            }
        )
    except ValidationError as error:
        signal_id = fields["SignalID"]
        detail = f"invalid Signal {signal_id}: {error}"
        raise ResearchInputError(detail=detail) from error


def _parse_enriched_signal(
    *,
    lines: list[str],
    topic: str,
    index: int,
) -> Mapping[str, str | Engagement]:
    heading = lines[0].strip()
    source_match = NUMBERED_SOURCE_PATTERN.match(
        next(
            (
                line.strip()
                for line in lines[1:]
                if NUMBERED_SOURCE_PATTERN.match(line.strip())
            ),
            "",
        ),
    )

    title_match = SOURCE_HEADER_PATTERN.match(heading)
    if title_match is None:
        raise ResearchInputError(detail=f"Signal block missing title: {heading}")

    signal_title = title_match.group("title").strip()
    signal_id = f"{_slug(topic)}-{index:03d}"

    if source_match is None:
        raise ResearchInputError(detail=f"Signal {signal_title} missing source line")

    source = source_match.group("source").strip().lower()
    url = ""
    observed_line = ""
    evidence = ""
    engagement = Engagement()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- URL:"):
            url = stripped.removeprefix("- URL:").strip()
        elif stripped.startswith("- Evidence:"):
            evidence = stripped.removeprefix("- Evidence:").strip()
        elif DATE_PREFIX_PATTERN.match(stripped):
            observed_line = stripped
            engagement = _parse_enriched_engagement(observed_line)

    if url == "":
        raise ResearchInputError(detail=f"Signal {signal_title} missing URL")

    if observed_line == "":
        raise ResearchInputError(detail=f"Signal {signal_title} missing observed date")

    observed_match = re.search(r"\d{4}-\d{2}-\d{2}", observed_line)
    if observed_match is None:
        raise ResearchInputError(detail=f"Signal {signal_title} missing observed date")

    return {
        "SignalID": signal_id,
        "Source": source,
        "URL": url,
        "Observed": observed_match.group(0),
        "Audience": f"contributors discussing {topic}",
        "Pain": signal_title,
        "Evidence": evidence or signal_title,
        "Engagement": engagement,
        "Business Relevance": "medium",
        "Confidence": "low",
        "Validation Needed": (
            "Validate user interviews before productizing this signal."
        ),
    }


def _parse_enriched_engagement(observed_line: str) -> Engagement:
    metrics: list[str] = re.findall(r"\[([^\]]+)\]", observed_line)
    if not metrics:
        return Engagement()

    values: dict[str, int | None] = {
        "upvotes": None,
        "comments": None,
        "likes": None,
        "views": None,
    }
    metric_text = metrics[0]
    if "pts" in metric_text:
        match = re.search(r"(\d+)pts", metric_text)
        if match is not None:
            values["upvotes"] = int(match.group(1))
    if "cmt" in metric_text:
        match = re.search(r"(\d+)cmt", metric_text)
        if match is not None:
            values["comments"] = int(match.group(1))
    if "likes" in metric_text:
        match = re.search(r"(\d+)likes", metric_text)
        if match is not None:
            values["likes"] = int(match.group(1))
    if "views" in metric_text:
        match = re.search(r"(\d+)views", metric_text)
        if match is not None:
            values["views"] = int(match.group(1))

    return Engagement(
        upvotes=values["upvotes"],
        comments=values["comments"],
        likes=values["likes"],
        views=values["views"],
    )


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


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
