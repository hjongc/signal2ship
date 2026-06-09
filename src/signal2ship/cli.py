from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, override

import typer
from pydantic import ValidationError
from typer.core import TyperGroup
from typer.models import ArgumentInfo, OptionInfo

if TYPE_CHECKING:
    from click import Context

from .app_generation import (
    AppGenerationError,
    approve_spec_packet,
    build_approved_app,
)
from .evidence import load_ledger
from .last30days import (
    Last30DaysRunError,
    Last30DaysUnavailableError,
    run_last30days,
)
from .lifecycle import ApprovalIntegrityError, RunLifecycleError
from .llm import (
    LLMClient,
    OpenRouterConfigError,
    build_openrouter_client,
)
from .openrouter_transport import OpenRouterRequestError
from .release import (
    AppVerificationError,
    DeploymentReadinessError,
    StorePackError,
    generate_store_pack,
    prepare_deployment_readiness_bundle,
    verify_generated_app,
)
from .research import ResearchInputError, load_research_ledger, write_ledger
from .runtime import build_local_run_manifest
from .supervisor import decide_after_research
from .workflow import (
    LLMClientFactory,
    WorkflowDependencyError,
    execute_local_workflow,
)

DECIDE_COMMAND: Final = "decide"
RESEARCH_COMMAND: Final = "research"
RUN_COMMAND: Final = "run"
APPROVE_SPEC_COMMAND: Final = "approve-spec"
BUILD_APPROVED_COMMAND: Final = "build-approved"
VERIFY_APP_COMMAND: Final = "verify-app"
PREPARE_DEPLOY_BUNDLE_COMMAND: Final = "prepare-deploy-bundle"
GENERATE_STORE_PACK_COMMAND: Final = "generate-store-pack"
DEFAULT_RESEARCH_OUTPUT: Final = Path("outputs/signals/evidence_ledger.json")
DEFAULT_WORKFLOW_OUTPUT_DIR: Final = Path("outputs")
DEFAULT_GENERATED_APP_DIR: Final = Path("apps/generated")
DEFAULT_SPEC_APPROVAL_OUTPUT: Final = Path("outputs/product/SPEC_APPROVAL.json")
DEFAULT_LLM_PROVIDER: Final = "openrouter"


class Signal2ShipGroup(TyperGroup):
    @override
    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            normalized_args = [DECIDE_COMMAND, *args]
        else:
            normalized_args = args
        return super().parse_args(ctx, normalized_args)


app = typer.Typer(
    add_completion=False,
    cls=Signal2ShipGroup,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)

LEDGER_ARGUMENT: Final[ArgumentInfo] = ArgumentInfo(default=...)
TOPIC_ARGUMENT: Final[ArgumentInfo] = ArgumentInfo(default=...)
SPEC_PACKET_ARGUMENT: Final[ArgumentInfo] = ArgumentInfo(default=...)
APPROVAL_ARGUMENT: Final[ArgumentInfo] = ArgumentInfo(default=...)
APP_CONTRACT_ARGUMENT: Final[ArgumentInfo] = ArgumentInfo(default=...)
VERIFICATION_RECORD_ARGUMENT: Final[ArgumentInfo] = ArgumentInfo(default=...)
RAW_FILE_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--raw-file",),
)
OUTPUT_OPTION: Final[OptionInfo] = OptionInfo(default=..., param_decls=("--output",))
USE_LAST30DAYS_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--use-last30days",),
)
OUTPUT_DIR_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--output-dir",),
)
APP_DIR_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--app-dir",),
)
APPROVAL_OUTPUT_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--output",),
)
OPERATOR_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--operator",),
)
APPROVAL_REASON_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--reason",),
)
APPROVED_AT_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--approved-at",),
)
LLM_PROVIDER_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--llm-provider",),
)
LLM_MODEL_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--llm-model",),
)
STORE_METADATA_OPTION: Final[OptionInfo] = OptionInfo(
    default=...,
    param_decls=("--metadata",),
)


@app.command(DECIDE_COMMAND, hidden=True)
def decide(
    ledger: Annotated[Path, LEDGER_ARGUMENT],
) -> None:
    if not ledger.is_file():
        typer.echo(f"ledger file does not exist: {ledger}", err=True)
        raise typer.Exit(1)

    try:
        decision = decide_after_research(load_ledger(ledger))
    except ValidationError as error:
        typer.echo(f"validation error: {error}", err=True)
        raise typer.Exit(1) from error

    typer.echo(decision.model_dump_json(indent=2))


@app.command(RESEARCH_COMMAND)
def research(
    topic: Annotated[str, TOPIC_ARGUMENT],
    raw_file: Annotated[Path | None, RAW_FILE_OPTION] = None,
    output: Annotated[Path, OUTPUT_OPTION] = DEFAULT_RESEARCH_OUTPUT,
    use_last30days: Annotated[bool, USE_LAST30DAYS_OPTION] = False,
) -> None:
    try:
        source = raw_file
        if source is None:
            if not use_last30days:
                typer.echo(
                    "research input error: pass --raw-file or --use-last30days",
                    err=True,
                )
                raise typer.Exit(1)
            source = run_last30days(topic, save_dir=Path("outputs/research"))

        ledger = load_research_ledger(source, topic)
        write_ledger(ledger, output)
    except (
        ResearchInputError,
        Last30DaysUnavailableError,
        Last30DaysRunError,
    ) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    signal_count = len(ledger.signals)
    message = f"completed research ledger generation: {output} ({signal_count} signals)"
    typer.echo(message)


@app.command(RUN_COMMAND)
def run_workflow(
    topic: Annotated[str, TOPIC_ARGUMENT],
    raw_file: Annotated[Path | None, RAW_FILE_OPTION] = None,
    output_dir: Annotated[Path, OUTPUT_DIR_OPTION] = DEFAULT_WORKFLOW_OUTPUT_DIR,
    app_dir: Annotated[Path, APP_DIR_OPTION] = DEFAULT_GENERATED_APP_DIR,
    llm_provider: Annotated[str, LLM_PROVIDER_OPTION] = DEFAULT_LLM_PROVIDER,
    llm_model: Annotated[str | None, LLM_MODEL_OPTION] = None,
) -> None:
    if raw_file is not None:
        try:
            workflow_result = execute_local_workflow(
                topic=topic,
                raw_file=raw_file,
                output_dir=output_dir,
                app_dir=app_dir,
                llm_client_factory=_build_llm_client_factory(
                    llm_provider,
                    llm_model,
                ),
            )
        except (
            ResearchInputError,
            OpenRouterConfigError,
            OpenRouterRequestError,
            WorkflowDependencyError,
        ) as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(1) from error

        typer.echo(workflow_result.model_dump_json(indent=2))
        return

    manifest = build_local_run_manifest(topic)
    typer.echo(manifest.model_dump_json(indent=2))


@app.command(APPROVE_SPEC_COMMAND)
def approve_spec(
    spec_packet: Annotated[Path, SPEC_PACKET_ARGUMENT],
    output: Annotated[
        Path,
        APPROVAL_OUTPUT_OPTION,
    ] = DEFAULT_SPEC_APPROVAL_OUTPUT,
    operator: Annotated[str, OPERATOR_OPTION] = "local-operator",
    reason: Annotated[
        str,
        APPROVAL_REASON_OPTION,
    ] = "Approved final idea/MVP spec for app creation.",
    approved_at: Annotated[str | None, APPROVED_AT_OPTION] = None,
) -> None:
    try:
        approval = approve_spec_packet(
            spec_packet_path=spec_packet,
            output_path=output,
            operator=operator,
            approval_reason=reason,
            approved_at=approved_at,
        )
    except (
        AppGenerationError,
        ApprovalIntegrityError,
        RunLifecycleError,
        ValidationError,
    ) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    typer.echo(approval.model_dump_json(indent=2))


@app.command(BUILD_APPROVED_COMMAND)
def build_approved(
    approval: Annotated[Path, APPROVAL_ARGUMENT],
    output_dir: Annotated[Path, OUTPUT_DIR_OPTION] = DEFAULT_WORKFLOW_OUTPUT_DIR,
    app_dir: Annotated[Path, APP_DIR_OPTION] = DEFAULT_GENERATED_APP_DIR,
) -> None:
    try:
        workflow_result = build_approved_app(
            approval_path=approval,
            output_dir=output_dir,
            app_dir=app_dir,
        )
    except (
        AppGenerationError,
        ApprovalIntegrityError,
        RunLifecycleError,
        ValidationError,
    ) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    typer.echo(workflow_result.model_dump_json(indent=2))


@app.command(VERIFY_APP_COMMAND)
def verify_app(
    app_contract: Annotated[Path, APP_CONTRACT_ARGUMENT],
    output_dir: Annotated[Path, OUTPUT_DIR_OPTION] = DEFAULT_WORKFLOW_OUTPUT_DIR,
) -> None:
    try:
        workflow_result = verify_generated_app(
            app_contract_path=app_contract,
            output_dir=output_dir,
        )
    except (
        AppVerificationError,
        RunLifecycleError,
        ValidationError,
    ) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    typer.echo(workflow_result.model_dump_json(indent=2))


@app.command(PREPARE_DEPLOY_BUNDLE_COMMAND)
def prepare_deploy_bundle(
    app_contract: Annotated[Path, APP_CONTRACT_ARGUMENT],
    verification_record: Annotated[Path, VERIFICATION_RECORD_ARGUMENT],
    output_dir: Annotated[Path, OUTPUT_DIR_OPTION] = DEFAULT_WORKFLOW_OUTPUT_DIR,
) -> None:
    try:
        workflow_result = prepare_deployment_readiness_bundle(
            app_contract_path=app_contract,
            verification_record_path=verification_record,
            output_dir=output_dir,
        )
    except (
        AppVerificationError,
        DeploymentReadinessError,
        RunLifecycleError,
        ValidationError,
    ) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    typer.echo(workflow_result.model_dump_json(indent=2))


@app.command(GENERATE_STORE_PACK_COMMAND)
def generate_store_pack_command(
    app_contract: Annotated[Path, APP_CONTRACT_ARGUMENT],
    verification_record: Annotated[Path, VERIFICATION_RECORD_ARGUMENT],
    metadata: Annotated[Path | None, STORE_METADATA_OPTION] = None,
    output_dir: Annotated[Path, OUTPUT_DIR_OPTION] = DEFAULT_WORKFLOW_OUTPUT_DIR,
) -> None:
    try:
        workflow_result = generate_store_pack(
            app_contract_path=app_contract,
            verification_record_path=verification_record,
            metadata_path=metadata,
            output_dir=output_dir,
        )
    except (
        AppVerificationError,
        DeploymentReadinessError,
        StorePackError,
        ValidationError,
    ) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    typer.echo(workflow_result.model_dump_json(indent=2))


def run() -> None:
    app()


def _build_llm_client_factory(
    llm_provider: str,
    llm_model: str | None,
) -> LLMClientFactory:
    match llm_provider:
        case "openrouter":

            def build_client() -> LLMClient:
                return build_openrouter_client(model_override=llm_model)

            return build_client
        case _:
            raise OpenRouterConfigError(
                detail="--llm-provider must be openrouter",
            )
