from __future__ import annotations

from typing import Final

SOURCE_URL_BASE: Final = "https://github.com/openai/codex/issues"

type JsonValue = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


def make_signal(index: int, relevance: str = "medium") -> dict[str, JsonValue]:
    return {
        "signal_id": f"sig_{index:03d}",
        "source": "github",
        "url": f"{SOURCE_URL_BASE}/{index + 1}",
        "observed_at": "2026-06-08",
        "audience": "developers using Codex CLI",
        "pain_point": "Recurring agent workflows are hard to control.",
        "evidence_summary": (
            "Users describe keeping recurring agent instructions consistent."
        ),
        "engagement": {"upvotes": 100 + index, "comments": 20 + index},
        "business_relevance": relevance,
        "confidence": "medium",
        "validation_needed": "Interview target users about workflow reliability.",
    }


def make_ledger(signal_count: int, relevance: str = "medium") -> dict[str, JsonValue]:
    return {
        "domain": "AI coding agent workflow",
        "generated_at": "2026-06-08",
        "signals": [
            make_signal(index=index, relevance=relevance)
            for index in range(signal_count)
        ],
    }


def make_last30days_markdown(
    *,
    signal_count: int = 15,
    relevance: str = "medium",
    include_url: bool = True,
) -> str:
    signal_blocks = [
        _make_last30days_signal_block(
            index=index,
            relevance=relevance,
            include_url=include_url,
        )
        for index in range(signal_count)
    ]
    return "\n\n".join(["Generated: 2026-06-08", *signal_blocks])


def _make_last30days_signal_block(
    *,
    index: int,
    relevance: str,
    include_url: bool,
) -> str:
    signal = make_signal(index=index, relevance=relevance)
    url_line = f"URL: {signal['url']}\n" if include_url else ""
    return (
        f"## Signal {signal['signal_id']}\n"
        f"Source: {signal['source']}\n"
        f"{url_line}"
        f"Observed: {signal['observed_at']}\n"
        f"Audience: {signal['audience']}\n"
        f"Pain: {signal['pain_point']}\n"
        f"Evidence: {signal['evidence_summary']}\n"
        f"Engagement: upvotes={100 + index} comments={20 + index}\n"
        f"Business Relevance: {relevance}\n"
        f"Confidence: {signal['confidence']}\n"
        f"Validation Needed: {signal['validation_needed']}"
    )


def make_last30days_markdown_v3(
    *,
    signal_count: int = 2,
) -> str:
    signals = [
        (
            "# last30days v3.3.2: AI tooling for solo builders\n\n"
            "- Date range: 2026-05-10 to 2026-06-09\n\n"
            "## Resolved Entities\n\n"
        )
    ]

    for index in range(signal_count):
        title = f"Signal title {index + 1}"
        signal_block = (
            "".join(
                [
                    f"### {index + 1}. {title} ",
                    f"(score {9 - index}, 1 item, sources: Reddit)\n",
                    f"1. [reddit] {title}\n",
                    f"   - 2026-06-0{index + 1} | reddit | [10pts, 2cmt, 100views] ",
                    f"| score:{9 - index}\n",
                    "   - URL: https://www.reddit.com/r/test/comments/",
                    f"{index + 1}/",
                    "example\n",
                    f"   - Evidence: {title} user reports pain.\n",
                ]
            )
        )
        signals.append(signal_block)
    return "\n\n".join(signals)
