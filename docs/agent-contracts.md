# Agent Contracts

## Task Envelope

Supervisor tasks must be structured.

```json
{
  "task_id": "task_001",
  "assigned_agent": "MarketResearchAgent",
  "objective": "Collect recent market signals for AI coding agent workflows.",
  "context": {
    "target_user": "developers using coding agents",
    "business_goal": "small paid app or local-first developer tool"
  },
  "instructions": [
    "Use /last30days for recent market signals.",
    "Focus on complaints, unmet needs, workaround behavior, and willingness-to-pay signals.",
    "Do not produce product ideas yet."
  ],
  "expected_outputs": [
    "outputs/research/raw_research.md",
    "outputs/research/source_index.json",
    "outputs/signals/evidence_ledger.json"
  ],
  "acceptance_criteria": [
    "At least 15 concrete market signals.",
    "Each signal includes source, audience, pain point, evidence summary, and confidence.",
    "Hype is separated from repeated pain."
  ]
}
```

## Agent Result Envelope

```json
{
  "task_id": "task_001",
  "agent": "MarketResearchAgent",
  "status": "completed",
  "summary": "Found repeated pain around controlling AI coding agents across recurring workflows.",
  "artifacts": [
    "outputs/research/raw_research.md",
    "outputs/research/source_index.json",
    "outputs/signals/evidence_ledger.json"
  ],
  "key_findings": [
    "Developers use manual prompt files as a workaround.",
    "Multi-repo coding-agent workflows are painful.",
    "Existing tools focus on code generation more than repeatable workflow governance."
  ],
  "risks": [
    "Some signals may indicate interest rather than willingness to pay."
  ],
  "next_recommendations": [
    "Score opportunities only after evidence confidence is checked."
  ]
}
```

## Evidence Ledger Shape

```json
{
  "signal_id": "sig_001",
  "source": "reddit",
  "url": "https://github.com/openai/codex/issues/1",
  "observed_at": "2026-06-08",
  "audience": "developers using AI coding agents",
  "pain_point": "Recurring agent workflows are hard to control.",
  "evidence_summary": "Users describe manually copying prompt files between tools.",
  "engagement": {
    "upvotes": 421,
    "comments": 89
  },
  "business_relevance": "medium",
  "confidence": "medium",
  "validation_needed": "Ask 3 target users whether this saves enough time to pay for."
}
```

## Scoring Criteria

Opportunity scoring should include:

- Pain intensity.
- Evidence strength.
- Target-user clarity.
- Willingness-to-pay signal.
- MVP buildability.
- Differentiation.
- Distribution path.
- Founder fit.

Ideas with weak evidence or broad MVP scope should be killed or reduced before build.
