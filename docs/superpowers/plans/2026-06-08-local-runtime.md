# Local Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Signal2Ship a local Codex Desktop-run agent harness, with OCI reserved for generated app preview deployment rather than the orchestrator runtime.

**Architecture:** Add a typed local run manifest that records stage order, runtime mode, approval gates, and deploy target policy. Expose it through `signal2ship run <topic>` so the current repo can start a bounded workflow without any server or frontend.

**Tech Stack:** Python 3.13+, Typer, Pydantic v2, pytest, ruff, basedpyright.

---

## File Structure

- Modify `docs/architecture.md`: clarify that the orchestrator is local and on demand.
- Modify `README.md`: replace the old next step with the local-runtime command.
- Modify `config/workflow.v1.yaml`: set Codex Desktop/local CLI as the default runtime and OCI as an optional generated-app deploy target.
- Modify `src/signal2ship/models.py`: add frozen Pydantic models for runtime stages and run manifests.
- Create `src/signal2ship/runtime.py`: build the deterministic local run manifest.
- Modify `src/signal2ship/cli.py`: add `signal2ship run <topic>`.
- Create `tests/test_runtime.py`: unit tests for manifest construction.
- Create `tests/test_run_cli.py`: CLI tests for observable local runtime behavior.

## Success Criteria

- `signal2ship run "AI coding agent workflow pain"` prints a JSON run manifest.
- The manifest says the orchestrator runs locally through Codex Desktop and local CLI.
- OCI is represented only as an optional generated-app preview deployment target.
- Production deployment, payments, public launch, and real user data collection require human approval.
- Existing `research` and `decide` commands keep passing.

---

### Task 1: Document The Local Runtime Decision

**Files:**
- Modify: `docs/architecture.md`
- Modify: `README.md`
- Modify: `config/workflow.v1.yaml`

- [ ] **Step 1: Update architecture wording**

Add a "Runtime Decision" section to `docs/architecture.md`:

```markdown
## Runtime Decision

Signal2Ship itself is a local, on-demand agent harness. Codex Desktop is the
operator-facing runtime, and the repository stores typed contracts, prompts,
artifacts, tests, and generated apps.

Do not deploy the Signal2Ship orchestrator as a server for v1. Use OCI only for
generated MVP app previews or for a later explicitly approved remote worker.
```

- [ ] **Step 2: Update workflow defaults**

In `config/workflow.v1.yaml`, represent the runtime policy:

```yaml
runtime:
  orchestrator: codex_desktop
  execution_mode: local_on_demand
  server_required: false
  frontend_required: false
```

- [ ] **Step 3: Run documentation inspection**

Run: `rg -n "Vercel|server|frontend|OCI|local" README.md docs config`

Expected: old Vercel default is removed or explicitly described as not the v1 orchestrator runtime.

### Task 2: Add Run Manifest Models

**Files:**
- Modify: `src/signal2ship/models.py`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Write the failing unit test**

Add to `tests/test_runtime.py`:

```python
from __future__ import annotations

from signal2ship.models import RuntimeMode
from signal2ship.runtime import build_local_run_manifest


def test_build_local_run_manifest_uses_codex_desktop_when_topic_is_given() -> None:
    # Given
    topic = "AI coding agent workflow pain"

    # When
    manifest = build_local_run_manifest(topic)

    # Then
    assert manifest.topic == topic
    assert manifest.runtime.mode is RuntimeMode.LOCAL_CODEX_DESKTOP
    assert manifest.runtime.server_required is False
    assert manifest.runtime.frontend_required is False
    assert manifest.deploy_target.name == "oci_preview_optional"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime.py::test_build_local_run_manifest_uses_codex_desktop_when_topic_is_given -q`

Expected: FAIL because `signal2ship.runtime` does not exist.

- [ ] **Step 3: Add minimal Pydantic models and builder**

Create enough code for the test to pass:

```python
class RuntimeMode(StrEnum):
    LOCAL_CODEX_DESKTOP = "local_codex_desktop"
```

```python
def build_local_run_manifest(topic: str) -> Signal2ShipRunManifest:
    return Signal2ShipRunManifest(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime.py::test_build_local_run_manifest_uses_codex_desktop_when_topic_is_given -q`

Expected: PASS.

### Task 3: Add Approval Gate Coverage

**Files:**
- Modify: `tests/test_runtime.py`
- Modify: `src/signal2ship/runtime.py`

- [ ] **Step 1: Write the failing approval-gate test**

Add:

```python
def test_build_local_run_manifest_blocks_production_actions_without_approval() -> None:
    # Given
    topic = "AI coding agent workflow pain"

    # When
    manifest = build_local_run_manifest(topic)

    # Then
    blocked = {gate.action for gate in manifest.human_approval_gates}
    assert blocked == {
        "production_deployment",
        "payments",
        "public_launch_posts",
        "real_user_data_collection",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime.py::test_build_local_run_manifest_blocks_production_actions_without_approval -q`

Expected: FAIL until approval gates are modeled.

- [ ] **Step 3: Implement approval gate fields**

Add `HumanApprovalGate` and include the four required actions.

- [ ] **Step 4: Run focused runtime tests**

Run: `uv run pytest tests/test_runtime.py -q`

Expected: PASS.

### Task 4: Add CLI Run Command

**Files:**
- Create: `tests/test_run_cli.py`
- Modify: `src/signal2ship/cli.py`

- [ ] **Step 1: Write failing CLI test**

Create `tests/test_run_cli.py`:

```python
from __future__ import annotations

from typer.testing import CliRunner

from signal2ship.cli import app
from signal2ship.models import Signal2ShipRunManifest


def test_run_cli_prints_local_runtime_manifest() -> None:
    # Given
    runner = CliRunner()

    # When
    result = runner.invoke(app, ["run", "AI coding agent workflow pain"])

    # Then
    assert result.exit_code == 0
    manifest = Signal2ShipRunManifest.model_validate_json(result.output)
    assert manifest.runtime.mode == "local_codex_desktop"
    assert manifest.deploy_target.name == "oci_preview_optional"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_cli.py::test_run_cli_prints_local_runtime_manifest -q`

Expected: FAIL because the `run` command is missing.

- [ ] **Step 3: Add the CLI command**

Add a Typer command:

```python
@app.command(RUN_COMMAND)
def run_workflow(topic: Annotated[str, TOPIC_ARGUMENT]) -> None:
    manifest = build_local_run_manifest(topic)
    typer.echo(manifest.model_dump_json(indent=2))
```

- [ ] **Step 4: Run focused CLI tests**

Run: `uv run pytest tests/test_run_cli.py tests/test_research_cli.py -q`

Expected: PASS.

### Task 5: Final Verification

**Files:**
- All changed files.

- [ ] **Step 1: Run full tests**

Run: `uv run pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Run lint**

Run: `uv run ruff check .`

Expected: no lint errors.

- [ ] **Step 3: Run format check**

Run: `uv run ruff format --check .`

Expected: all files already formatted.

- [ ] **Step 4: Run typecheck**

Run: `uv run basedpyright`

Expected: 0 errors.

- [ ] **Step 5: Inspect final diff**

Run: `git diff --stat`

Expected: only local-runtime docs, config, models, runtime, CLI, and tests changed.
