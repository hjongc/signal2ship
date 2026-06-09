# Signal2Ship Architecture

## Shape

Signal2Ship uses a supervisor loop rather than a fixed graph.

```text
Supervisor
  -> assigns task
  -> receives artifacts
  -> evaluates acceptance criteria
  -> requests revision, advances, kills, or asks for human approval
```

The graph is an internal runtime detail. The user-facing model is an agent organization with explicit artifacts and gates.

## Runtime Decision

Signal2Ship itself is a local, on-demand agent harness. Codex Desktop is the
operator-facing runtime, and the repository stores typed contracts, prompts,
artifacts, tests, and generated apps.

LLM-backed stage guidance uses OpenRouter for pre-approval workflow runs.
The API key must come from `OPENROUTER_API_KEY` in the process environment or
local `.env`; the Flash model is supplied by `--llm-model`,
`OPENROUTER_FLASH_MODEL`, or the legacy `OPENROUTER_MODEL`. The Pro model is
supplied by `OPENROUTER_PRO_MODEL` or the legacy `OPENROUTER_MODEL_PRO`.
The recommended v1 routing is `deepseek/deepseek-v4-flash` for lightweight
stage guidance and `deepseek/deepseek-v4-pro` for deeper judgment stages.

Do not deploy the Signal2Ship orchestrator as a server for v1. Use OCI only for
generated MVP app previews or for a later explicitly approved remote worker.

## Core Artifacts

- `outputs/research/raw_research.md`: raw or lightly cleaned research output.
- `outputs/research/source_index.json`: source metadata and links.
- `outputs/signals/evidence_ledger.json`: structured market signals.
- `outputs/ideas/scored_ideas.md`: ranked opportunities with reasoning.
- `outputs/ideas/opportunity_scores.json`: structured top opportunity score.
- `outputs/product/MVP_SPEC.md`: narrow product scope.
- `outputs/product/IDEA_SPEC_APPROVAL.json`: machine-readable final idea/MVP
  spec packet that must be explicitly approved before app creation.
- `outputs/product/IDEA_SPEC_APPROVAL.md`: human-reviewable copy of the final
  idea/MVP spec packet.
- `outputs/product/SPEC_APPROVAL.json`: explicit approval record containing the
  approved packet hash, approving operator, and allowed next state.
- `apps/generated/<app>/`: generated MVP app project files created only after
  spec approval.
- `apps/generated/<app>/APP_CONTRACT.json`: generated app contract with stack,
  command manifest, expected artifacts, and minimum runnable check.
- `outputs/reviews/VERIFICATION_RECORD.json`: generated app command outcome
  record.
- `outputs/reviews/POLICY_READINESS.json`: policy/privacy readiness metadata
  citing official Apple and Google source URLs.
- `outputs/store/STORE_PACK.json`: machine-readable Apple App Store and Google
  Play preparation pack generated after app verification.
- `outputs/store/STORE_PACK.md`: human-readable store preparation checklist,
  blockers, official source URLs, and explicit no-submission boundary.
- `outputs/launch/DEPLOYMENT_BUNDLE.json`: release-readiness state packet that
  requires deployment approval before any release action.
- `outputs/launch/OCI_PREVIEW_BUNDLE.md`: OCI preview deployment bundle draft
  that requires human approval before execution.

Workflow runs should use fresh `/last30days` raw research artifacts. Missing
research capability, weak evidence, or missing OpenRouter configuration must
surface as a failed command instead of generating substitute artifacts.

## Main Loop

```text
1. Load goal, constraints, and current artifacts.
2. Decide the next task.
3. Assign the task to one agent with acceptance criteria.
4. Save returned artifacts.
5. Evaluate artifacts.
6. Revise, advance, kill, or request approval.
```

## Required Gates

### Research Gate

Continue only when evidence is recent, sourced, specific, and repeated enough to support opportunity analysis.

### Opportunity Gate

Continue only when one idea has a clear target user, repeated pain, plausible willingness to pay, low MVP complexity, and a distribution path.

### Build Gate

Continue only when the MVP spec is small enough to build in one focused implementation pass.

### Spec Approval Gate

Raw research runs with enough evidence stop at `needs_spec_approval`. App
creation can start only when `approve-spec` writes a matching approval record
for the unchanged `IDEA_SPEC_APPROVAL.json` packet.

### Approved App Creation Gate

`build-approved` reads only the approved packet, verifies the approval hash,
run ID, and next allowed state, then generates the app project and contract.
If the packet changes after approval, app creation fails visibly.

### Verification Gate

`verify-app` runs the generated app contract's minimum runnable check and
records command outcomes. A failed command writes a failed verification record
and blocks deployment-readiness preparation.

### Release Gate

Deployment-readiness bundle generation can be automated after verification
passes. Running the deployment on OCI, production deployment, App Store or
Google Play submission, payments, public posts, and real user data collection
require human approval.

### Store Pack Gate

`generate-store-pack` can prepare Apple App Store and Google Play metadata
artifacts after verification passes. The generated pack is a preparation
artifact only: missing listing, privacy, SDK, account deletion, asset,
permission, payment, content, review access, backend, or native/mobile
packaging evidence is surfaced as blockers. The command must not submit to App
Store Connect or Google Play Console, look up credentials, deploy, enable
payments, or collect real user data.

## Bounded Execution

Every run should define:

- Maximum research queries.
- Maximum revision count per stage.
- Maximum build scope.
- Required approval points.
- Stop reason when a gate fails.
