from signal2ship.research import parse_last30days_markdown
from tests.fixtures import make_last30days_markdown_v3


def test_parse_last30days_markdown_supports_enriched_last30days_v3_blocks() -> None:
    # Given
    raw = make_last30days_markdown_v3(signal_count=2)

    # When
    ledger = parse_last30days_markdown(raw, topic="solo dev pipeline")

    # Then
    assert ledger.generated_at == "2026-06-09"
    assert len(ledger.signals) == 2
    assert ledger.signals[0].signal_id == "solo-dev-pipeline-000"
    assert ledger.signals[0].source == "reddit"
    assert ledger.signals[0].observed_at == "2026-06-01"
    assert ledger.signals[0].engagement.upvotes == 10
    assert ledger.signals[0].engagement.comments == 2
    assert ledger.signals[0].engagement.views == 100


def test_parse_last30days_markdown_uses_enriched_audience_fallback() -> None:
    # Given
    raw = make_last30days_markdown_v3(signal_count=1)

    # When
    ledger = parse_last30days_markdown(raw, topic="solo dev pipeline")

    # Then
    assert ledger.signals[0].audience == "contributors discussing solo dev pipeline"
