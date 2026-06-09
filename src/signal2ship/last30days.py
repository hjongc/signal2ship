from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, override

SKILL_DIR_ENV: Final = "SIGNAL2SHIP_LAST30DAYS_SKILL_DIR"
INSTALL_COMMAND: Final = "npx skills add mvanhorn/last30days-skill -g"
DEFAULT_SKILL_DIR: Final = Path.home() / ".codex" / "skills" / "last30days"
TRUSTSTORE_RUNNER: Final = (
    "import runpy, sys\n"
    "import truststore\n"
    "truststore.inject_into_ssl()\n"
    "script = sys.argv[1]\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


@dataclass(frozen=True, slots=True)
class Last30DaysUnavailableError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return (
            f"last30days unavailable: {self.detail}. Install with "
            f"`{INSTALL_COMMAND}` and restart Codex to load the skill."
        )


@dataclass(frozen=True, slots=True)
class Last30DaysRunError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"last30days run failed: {self.detail}"


def resolve_skill_dir() -> Path:
    configured = os.environ.get(SKILL_DIR_ENV)
    if configured is not None and configured != "":
        return Path(configured)
    return DEFAULT_SKILL_DIR


def resolve_engine_script() -> Path:
    skill_dir = resolve_skill_dir()
    script = skill_dir / "scripts" / "last30days.py"
    if script.is_file():
        return script
    raise Last30DaysUnavailableError(
        detail=f"expected engine script at {script}",
    )


def run_last30days(topic: str, save_dir: Path) -> Path:
    script = resolve_engine_script()
    save_dir.mkdir(parents=True, exist_ok=True)
    before = set(save_dir.glob("*-raw*.md"))
    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            TRUSTSTORE_RUNNER,
            str(script),
            topic,
            "--save-dir",
            str(save_dir),
            "--save-suffix",
            "signal2ship",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise Last30DaysRunError(detail=detail)

    created = sorted(
        set(save_dir.glob("*-raw*.md")) - before,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if created:
        return created[0]

    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    candidates = sorted(
        save_dir.glob(f"{slug}-raw*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]

    raise Last30DaysRunError(
        detail=f"engine completed but no raw markdown file was found in {save_dir}",
    )
