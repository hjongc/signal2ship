# AGENTS.md

## Scope

These instructions apply to the `Signal2Ship/` project.

## Language

Agent-facing project documents, prompts, plans, code comments, commit messages, and PR text must be written in English unless the user explicitly asks otherwise.

## Project Intent

Signal2Ship turns fresh market signals into small, shippable app MVPs.

The project should stay biased toward narrow, verifiable workflows:

1. Research recent market signals.
2. Convert evidence into opportunity candidates.
3. Pick one constrained MVP.
4. Build only the MVP.
5. Verify through tests and actual app usage.
6. Deploy preview only unless the user approves production launch.

## Operating Rules

- Treat `/last30days` as a research capability owned by the Market Research Agent, not as the whole product.
- Keep an evidence ledger between research and product decisions.
- Do not build from weak evidence. Add a kill or continue decision before PRD creation.
- Do not activate payments, publish launch posts, deploy production, or store real user data without explicit user approval.
- Prefer one small working app over a broad platform.
- Keep outputs traceable: every product requirement should point back to evidence or a user constraint.

## v1 Stack Assumptions

- Orchestration can start as a local CLI or Codex-run workflow before becoming a web app.
- Signal2Ship itself should not require a server or frontend for v1.
- Generated MVP apps should default to Next.js, TypeScript, Tailwind, and an OCI preview bundle unless a specific idea requires another stack.
- Supabase is optional and should be introduced only when persistence or auth is required by the selected MVP.

## Verification

For non-trivial changes, report:

- Changed files.
- Validation commands or manual checks performed.
- What could not be verified.
- Residual risks.
