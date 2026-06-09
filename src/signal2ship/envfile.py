from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import override

QUOTED_VALUE_MIN_LENGTH = 2


@dataclass(frozen=True, slots=True)
class DotenvLoadError(Exception):
    path: Path
    line_number: int
    detail: str

    @override
    def __str__(self) -> str:
        return f"{self.path}:{self.line_number}: {self.detail}"


def load_dotenv_environment(
    base_environ: Mapping[str, str],
    *,
    dotenv_path: Path,
) -> Mapping[str, str]:
    dotenv_values = _read_dotenv_values(dotenv_path)
    merged = dict(dotenv_values)
    merged.update(base_environ)
    return merged


def _read_dotenv_values(dotenv_path: Path) -> Mapping[str, str]:
    if not dotenv_path.exists():
        return {}
    if not dotenv_path.is_file():
        raise DotenvLoadError(
            path=dotenv_path,
            line_number=0,
            detail="expected a file",
        )

    values: dict[str, str] = {}
    with dotenv_path.open(encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            parsed = _parse_dotenv_line(
                raw_line,
                path=dotenv_path,
                line_number=line_number,
            )
            if parsed is not None:
                key, value = parsed
                values[key] = value
    return values


def _parse_dotenv_line(
    raw_line: str,
    *,
    path: Path,
    line_number: int,
) -> tuple[str, str] | None:
    stripped = raw_line.strip()
    if stripped == "" or stripped.startswith("#"):
        return None

    assignment = stripped.removeprefix("export ").strip()
    key, separator, value = assignment.partition("=")
    normalized_key = key.strip()
    if separator == "" or normalized_key == "":
        raise DotenvLoadError(
            path=path,
            line_number=line_number,
            detail="expected KEY=VALUE",
        )
    if not _is_valid_key(normalized_key):
        raise DotenvLoadError(
            path=path,
            line_number=line_number,
            detail=f"invalid key {normalized_key!r}",
        )

    return normalized_key, _clean_value(value.strip())


def _is_valid_key(key: str) -> bool:
    if key[0].isdigit():
        return False
    return key.replace("_", "").isalnum()


def _clean_value(value: str) -> str:
    if (
        len(value) >= QUOTED_VALUE_MIN_LENGTH
        and value[0] == value[-1]
        and value[0] in {"'", '"'}
    ):
        return value[1:-1]
    return value
