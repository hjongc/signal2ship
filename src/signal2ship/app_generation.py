from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, override

from pydantic import ValidationError

from .lifecycle import (
    ApprovalIntegrityError,
    content_sha256,
    require_approved_build_start,
    require_transition,
)
from .models import (
    ApprovalPacket,
    GeneratedAppCommand,
    GeneratedAppContract,
    IdeaSpecApprovalPacket,
    RunState,
    Signal2ShipWorkflowResult,
)

APP_CONTRACT_FILENAME: Final = "APP_CONTRACT.json"
COMMAND_MANIFEST_FILENAME: Final = "command-manifest.json"
SMOKE_SCRIPT_PATH: Final = "scripts/smoke.mjs"
GENERATOR_NAME: Final = "signal2ship.nextjs.template.v1"
SLUG_PATTERN: Final = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class AppGenerationError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"app generation error: {self.detail}"


def approve_spec_packet(
    *,
    spec_packet_path: Path,
    output_path: Path,
    operator: str,
    approval_reason: str,
    approved_at: str | None = None,
) -> ApprovalPacket:
    canonical_spec_packet_path = _canonical_existing_file(spec_packet_path)
    packet_content = _read_text(canonical_spec_packet_path)
    packet = _validate_spec_packet(packet_content, canonical_spec_packet_path)

    require_transition(packet.state, RunState.SPEC_APPROVED)
    if packet.approved_app_creation_state is not RunState.CREATING_APP:
        raise ApprovalIntegrityError(
            detail=(
                "spec packet approved_app_creation_state must be creating_app "
                "before approval"
            ),
        )

    approval = ApprovalPacket(
        run_id=packet.run_id,
        artifact_path=str(canonical_spec_packet_path),
        content_hash=content_sha256(packet_content),
        artifact_version="idea_spec_approval_packet.v1",
        operator=operator,
        approved_at=approved_at or _now_utc(),
        allowed_next_state=RunState.CREATING_APP,
        approval_reason=approval_reason,
    )
    _write_text(output_path, approval.model_dump_json(indent=2))
    return approval


def build_approved_app(
    *,
    approval_path: Path,
    output_dir: Path,
    app_dir: Path,
) -> Signal2ShipWorkflowResult:
    approval_content = _read_text(approval_path)
    try:
        approval = ApprovalPacket.model_validate_json(approval_content)
    except ValidationError as error:
        raise AppGenerationError(
            detail=f"invalid approval record: {approval_path}",
        ) from error

    spec_packet_path = _resolve_artifact_path(approval.artifact_path)
    spec_packet_content = _read_text(spec_packet_path)
    spec_packet = _validate_spec_packet(spec_packet_content, spec_packet_path)

    if spec_packet.state is not RunState.NEEDS_SPEC_APPROVAL:
        raise ApprovalIntegrityError(
            detail="approved packet must still be in needs_spec_approval state",
        )

    require_approved_build_start(
        current_state=RunState.SPEC_APPROVED,
        approval=approval,
        run_id=spec_packet.run_id,
        approved_artifact_content=spec_packet_content,
    )

    app_slug = _slugify(spec_packet.idea)
    app_root = _canonical_output_dir(app_dir / app_slug)
    if app_root.exists():
        raise AppGenerationError(
            detail=(
                "generated app output already exists; refusing to overwrite "
                f"{app_root}"
            ),
        )

    contract = _build_generated_app_contract(
        app_root=app_root,
        approval=approval,
    )
    artifacts = _write_nextjs_app(
        app_root=app_root,
        packet=spec_packet,
        contract=contract,
    )

    return Signal2ShipWorkflowResult(
        status="app_generated",
        selected_opportunity=app_slug,
        artifacts=[str(artifact) for artifact in artifacts],
        output_dir=str(output_dir),
        app_dir=str(app_root),
        reason=(
            "Approved spec hash matched. Generated app project contract, "
            "command manifest, and runnable smoke check artifacts."
        ),
        run_id=spec_packet.run_id,
        run_state=RunState.CREATING_APP,
        approval_packet=approval.artifact_path,
        approval_packet_hash=approval.content_hash,
        app_contract=str(app_root / APP_CONTRACT_FILENAME),
    )


def _build_generated_app_contract(
    *,
    app_root: Path,
    approval: ApprovalPacket,
) -> GeneratedAppContract:
    commands = [
        GeneratedAppCommand(
            name="install",
            command="npm install",
            required=True,
            purpose="Install generated Next.js app dependencies.",
        ),
        GeneratedAppCommand(
            name="test",
            command="npm test",
            required=True,
            purpose="Run the dependency-free generated app smoke check.",
        ),
        GeneratedAppCommand(
            name="typecheck",
            command="npm run typecheck",
            required=True,
            purpose="Type-check the generated TypeScript app.",
        ),
        GeneratedAppCommand(
            name="lint",
            command="npm run lint",
            required=True,
            purpose="Lint the generated Next.js app.",
        ),
        GeneratedAppCommand(
            name="build",
            command="npm run build",
            required=True,
            purpose="Build the generated app for preview.",
        ),
        GeneratedAppCommand(
            name="preview",
            command="npm run preview",
            required=False,
            purpose="Serve the generated app locally for manual usage checks.",
        ),
    ]
    return GeneratedAppContract(
        run_id=approval.run_id,
        app_type="web",
        output_root=str(app_root),
        stack=["Next.js", "TypeScript", "Tailwind CSS"],
        package_manager="npm",
        commands=commands,
        expected_artifacts=[
            "package.json",
            "next.config.ts",
            "tsconfig.json",
            "postcss.config.mjs",
            "eslint.config.mjs",
            "src/app/layout.tsx",
            "src/app/page.tsx",
            "src/app/globals.css",
            SMOKE_SCRIPT_PATH,
            COMMAND_MANIFEST_FILENAME,
            APP_CONTRACT_FILENAME,
        ],
        minimum_runnable_check="npm test",
        preview_instructions=[
            "Run npm install inside the generated app directory.",
            "Run npm test for the dependency-free smoke check.",
            "Run npm run build before considering the preview verified.",
            "Run npm run preview for local browser verification.",
        ],
        source_approval_packet=approval.artifact_path,
        source_approval_hash=approval.content_hash,
        generator=GENERATOR_NAME,
        generated_at=_now_utc(),
    )


def _write_nextjs_app(
    *,
    app_root: Path,
    packet: IdeaSpecApprovalPacket,
    contract: GeneratedAppContract,
) -> list[Path]:
    command_manifest = app_root / COMMAND_MANIFEST_FILENAME
    contract_path = app_root / APP_CONTRACT_FILENAME
    artifacts = [
        app_root / "package.json",
        app_root / "next.config.ts",
        app_root / "tsconfig.json",
        app_root / "postcss.config.mjs",
        app_root / "eslint.config.mjs",
        app_root / "src" / "app" / "layout.tsx",
        app_root / "src" / "app" / "page.tsx",
        app_root / "src" / "app" / "globals.css",
        app_root / SMOKE_SCRIPT_PATH,
        command_manifest,
        contract_path,
    ]

    _write_json(app_root / "package.json", _package_json(_slugify(packet.idea)))
    _write_text(app_root / "next.config.ts", _next_config())
    _write_json(app_root / "tsconfig.json", _tsconfig())
    _write_text(app_root / "postcss.config.mjs", _postcss_config())
    _write_text(app_root / "eslint.config.mjs", _eslint_config())
    _write_text(app_root / "src" / "app" / "layout.tsx", _layout_tsx(packet))
    _write_text(app_root / "src" / "app" / "page.tsx", _page_tsx(packet))
    _write_text(app_root / "src" / "app" / "globals.css", _globals_css())
    _write_text(app_root / SMOKE_SCRIPT_PATH, _smoke_script(packet, contract))
    _write_text(
        command_manifest,
        json.dumps(
            [command.model_dump() for command in contract.commands],
            indent=2,
        ),
    )
    _write_text(contract_path, contract.model_dump_json(indent=2))
    return artifacts


def _package_json(slug: str) -> dict[str, object]:
    return {
        "name": slug,
        "version": "0.1.0",
        "private": True,
        "type": "module",
        "scripts": {
            "test": "node scripts/smoke.mjs",
            "typecheck": "tsc --noEmit",
            "lint": "eslint .",
            "build": "next build",
            "preview": "next dev --hostname 127.0.0.1",
        },
        "dependencies": {
            "next": "16.2.7",
            "react": "19.2.7",
            "react-dom": "19.2.7",
        },
        "devDependencies": {
            "@tailwindcss/postcss": "4.3.0",
            "@types/node": "25.9.2",
            "@types/react": "19.2.17",
            "eslint": "10.4.1",
            "eslint-config-next": "16.2.7",
            "tailwindcss": "4.3.0",
            "typescript": "6.0.3",
        },
    }


def _next_config() -> str:
    return """import type { NextConfig } from 'next';

const nextConfig: NextConfig = {};

export default nextConfig;
"""


def _tsconfig() -> dict[str, object]:
    return {
        "compilerOptions": {
            "target": "ES2017",
            "lib": ["dom", "dom.iterable", "esnext"],
            "allowJs": True,
            "skipLibCheck": True,
            "strict": True,
            "noEmit": True,
            "esModuleInterop": True,
            "module": "esnext",
            "moduleResolution": "bundler",
            "resolveJsonModule": True,
            "isolatedModules": True,
            "jsx": "preserve",
            "incremental": True,
            "plugins": [{"name": "next"}],
        },
        "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
        "exclude": ["node_modules"],
    }


def _postcss_config() -> str:
    return """const config = {
  plugins: {
    '@tailwindcss/postcss': {},
  },
};

export default config;
"""


def _eslint_config() -> str:
    return """import nextVitals from 'eslint-config-next/core-web-vitals';

export default [...nextVitals];
"""


def _layout_tsx(packet: IdeaSpecApprovalPacket) -> str:
    title = json.dumps(packet.idea)
    return f"""import type {{ Metadata }} from 'next';
import './globals.css';

export const metadata: Metadata = {{
  title: {title},
  description: 'Generated by Signal2Ship from an approved MVP spec.',
}};

export default function RootLayout({{
  children,
}}: Readonly<{{
  children: React.ReactNode;
}}>) {{
  return (
    <html lang="en">
      <body>{{children}}</body>
    </html>
  );
}}
"""


def _page_tsx(packet: IdeaSpecApprovalPacket) -> str:
    idea = json.dumps(packet.idea)
    target_user = json.dumps(packet.target_user)
    core_problem = json.dumps(packet.core_problem)
    mvp_scope = json.dumps(packet.mvp_scope, indent=2)
    non_goals = json.dumps(packet.non_goals, indent=2)
    policy_notes = json.dumps(packet.policy_privacy_notes, indent=2)
    return f"""const idea = {idea};
const targetUser = {target_user};
const coreProblem = {core_problem};
const mvpScope = {mvp_scope};
const nonGoals = {non_goals};
const policyNotes = {policy_notes};

export default function Home() {{
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-10 px-6 py-12">
      <section className="rounded-3xl bg-slate-950 px-8 py-10 text-white shadow-2xl">
        <p className="text-sm uppercase tracking-[0.3em] text-cyan-300">
          Signal2Ship approved MVP
        </p>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight">{{idea}}</h1>
        <p className="mt-4 max-w-3xl text-lg text-slate-200">{{coreProblem}}</p>
      </section>
      <section className="grid gap-6 md:grid-cols-2">
        <Card title="Target user" items={{[targetUser]}} />
        <Card title="MVP scope" items={{mvpScope}} />
        <Card title="Non-goals" items={{nonGoals}} />
        <Card title="Policy / privacy notes" items={{policyNotes}} />
      </section>
    </main>
  );
}}

function Card({{
  title,
  items,
}}: Readonly<{{
  title: string;
  items: string[];
}}>) {{
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-xl font-semibold text-slate-950">{{title}}</h2>
      <ul className="mt-4 space-y-3 text-slate-700">
        {{items.map((item) => (
          <li key={{item}} className="rounded-xl bg-slate-50 px-4 py-3">
            {{item}}
          </li>
        ))}}
      </ul>
    </article>
  );
}}
"""


def _globals_css() -> str:
    return """@import "tailwindcss";

:root {
  color-scheme: light;
}

body {
  margin: 0;
  background: #f8fafc;
  color: #0f172a;
  font-family: Arial, Helvetica, sans-serif;
}
"""


def _smoke_script(
    packet: IdeaSpecApprovalPacket,
    contract: GeneratedAppContract,
) -> str:
    expected_artifacts = json.dumps(contract.expected_artifacts, indent=2)
    run_id = json.dumps(packet.run_id)
    return f"""import {{ existsSync }} from 'node:fs';
import {{ join }} from 'node:path';

const expectedArtifacts = {expected_artifacts};
const runId = {run_id};
const missingArtifacts = expectedArtifacts.filter(
  (artifact) => !existsSync(join(process.cwd(), artifact)),
);

if (missingArtifacts.length > 0) {{
  console.error(`missing generated artifacts: ${{missingArtifacts.join(', ')}}`);
  process.exit(1);
}}

console.log(`Signal2Ship generated app smoke passed for run ${{runId}}.`);
"""


def _resolve_artifact_path(artifact_path: str) -> Path:
    path = Path(artifact_path)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _canonical_existing_file(path: Path) -> Path:
    if not path.is_file():
        raise AppGenerationError(detail=f"required file does not exist: {path}")
    return path.expanduser().resolve(strict=True)


def _canonical_output_dir(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.lower()).strip("-")
    if slug == "":
        raise AppGenerationError(detail="could not derive generated app slug")
    return slug


def _validate_spec_packet(
    packet_content: str,
    packet_path: Path,
) -> IdeaSpecApprovalPacket:
    try:
        return IdeaSpecApprovalPacket.model_validate_json(packet_content)
    except ValidationError as error:
        raise AppGenerationError(
            detail=f"invalid idea/spec approval packet: {packet_path}",
        ) from error


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise AppGenerationError(detail=f"required file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload, indent=2))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _now_utc() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()
