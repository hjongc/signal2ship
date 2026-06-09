# Signal2Ship

Turn fresh market signals into shippable apps.

Signal2Ship is a personal, terminal-first app factory for finding recent,
evidence-backed business opportunities and turning one approved narrow
opportunity into a generated MVP preview.

## Concept

Signal2Ship is not a fixed node pipeline. It is a supervisor-led agent organization:

```text
market signal -> evidence ledger -> opportunity scoring -> MVP spec approval
  -> approved app build -> verification -> store/deployment-readiness bundles
```

The supervisor decides the next task, delegates to specialist agents, checks artifacts against acceptance criteria, and requests revision when the evidence or app is not good enough.

## v1 Agents

- Venture Supervisor Agent: owns decisions, gates, and task routing.
- Market Research Agent: uses `/last30days` and related source checks to collect recent evidence.
- Opportunity Analyst Agent: turns evidence into ranked business opportunities.
- Product Scope Agent: narrows one opportunity into a buildable MVP.
- App Builder Agent: builds the MVP against the scope.
- QA / Release Critic Agent: verifies the app and blocks release when needed.

## Hard Gates

- Do not generate product ideas until enough recent evidence exists.
- Do not write a PRD unless one opportunity passes the kill or continue gate.
- Do not build an app until the final idea/MVP spec approval packet is
  explicitly approved.
- Do not build broad platforms. Reduce scope first.
- Do not deploy production, submit to app stores, enable payments, or publish
  public launch material without human approval.

## Current State

This repository currently contains the v1 workflow scaffold:

- `docs/` for concept, architecture, and agent contracts.
- `prompts/` for agent prompt drafts.
- `config/workflow.v1.yaml` for the initial workflow contract.
- `outputs/` for generated research, ideas, specs, reviews, and launch assets.
- `apps/generated/` for MVP app outputs.

## Next Step

Run the local workflow manifest:

```bash
uv run signal2ship run "AI coding agent workflow pain"
```

Install and use the `/last30days` research capability for fresh evidence:

```bash
uv run signal2ship research "AI coding agent workflow pain" \
  --use-last30days \
  --output outputs/signals/evidence_ledger.json
```

The command fails if the installed `/last30days` skill is unavailable or if the
research output lacks source-backed signals.

Configure OpenRouter with a local `.env` file:

```bash
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_FLASH_MODEL=deepseek/deepseek-v4-flash
OPENROUTER_PRO_MODEL=deepseek/deepseek-v4-pro
OPENROUTER_APP_TITLE=Signal2Ship
```

Signal2Ship routes lighter stage guidance to
`deepseek/deepseek-v4-flash`. Deeper judgment stages, currently Opportunity
Analyst and QA / Release Critic, use `deepseek/deepseek-v4-pro`.

Run the pre-approval workflow with a fresh raw research markdown file produced
by `/last30days`:

```bash
uv run signal2ship run "AI coding agent workflow pain" \
  --raw-file outputs/research/<fresh-last30days-raw.md> \
  --llm-provider openrouter
```

When evidence is strong enough, this stops at `needs_spec_approval` and writes:

- `outputs/product/MVP_SPEC.md`
- `outputs/product/IDEA_SPEC_APPROVAL.json`
- `outputs/product/IDEA_SPEC_APPROVAL.md`

It does not create an app directory before explicit spec approval.

Approve the reviewed idea/spec packet:

```bash
uv run signal2ship approve-spec \
  outputs/product/IDEA_SPEC_APPROVAL.json \
  --output outputs/product/SPEC_APPROVAL.json \
  --operator hjongc \
  --reason "Approved final MVP scope."
```

Build only from the approved packet:

```bash
uv run signal2ship build-approved \
  outputs/product/SPEC_APPROVAL.json \
  --output-dir outputs \
  --app-dir apps/generated
```

Verify the generated app and prepare store/deployment-readiness bundles:

```bash
uv run signal2ship verify-app \
  apps/generated/<app-slug>/APP_CONTRACT.json \
  --output-dir outputs

uv run signal2ship generate-store-pack \
  apps/generated/<app-slug>/APP_CONTRACT.json \
  outputs/reviews/VERIFICATION_RECORD.json \
  --metadata outputs/store/STORE_METADATA.json \
  --output-dir outputs

uv run signal2ship prepare-deploy-bundle \
  apps/generated/<app-slug>/APP_CONTRACT.json \
  outputs/reviews/VERIFICATION_RECORD.json \
  --output-dir outputs
```

`generate-store-pack` writes Apple App Store and Google Play preparation
artifacts to `outputs/store/STORE_PACK.json` and `outputs/store/STORE_PACK.md`.
Missing metadata is reported as blockers and a non-ready status. The command
does not connect to App Store Connect or Google Play Console and does not
submit an app.

`prepare-deploy-bundle` writes policy/readiness artifacts and stops at
`needs_deploy_approval`. It does not run OCI deployment, App Store submission,
Google Play submission, payments, public launch posting, or real user data
collection.

The raw-research workflow does not generate approval artifacts without
configured OpenRouter stage guidance.

Signal2Ship itself runs on demand through Codex Desktop and the local CLI. It
does not need a server or frontend in v1. OCI is reserved for optional preview
deployment of generated MVP apps after QA and human approval.
