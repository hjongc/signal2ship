from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from signal2ship.last30days import run_last30days

if TYPE_CHECKING:
    import pytest


def test_run_last30days_injects_truststore_before_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    skill_dir = tmp_path / "last30days"
    script_dir = skill_dir / "scripts"
    output_dir = tmp_path / "outputs"
    marker_path = tmp_path / "ssl-context-module.txt"
    script_dir.mkdir(parents=True)
    script = script_dir / "last30days.py"
    _ = script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import ssl",
                "import sys",
                f"marker = Path({str(marker_path)!r})",
                "marker.write_text(ssl.SSLContext.__module__, encoding='utf-8')",
                "save_dir = Path(sys.argv[sys.argv.index('--save-dir') + 1])",
                "save_dir.mkdir(parents=True, exist_ok=True)",
                "raw_path = save_dir / 'topic-raw-signal2ship.md'",
                "raw_path.write_text('raw', encoding='utf-8')",
            ],
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SIGNAL2SHIP_LAST30DAYS_SKILL_DIR", str(skill_dir))

    # When
    raw_path = run_last30days("topic", save_dir=output_dir)

    # Then
    assert raw_path == output_dir / "topic-raw-signal2ship.md"
    assert marker_path.read_text(encoding="utf-8") == "truststore._api"
