"""Create an installable Blender addon archive with required shared contracts."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
REPOSITORY = PROJECT.parent
ADDON_SOURCE = PROJECT / "asset_validator"
SHARED_SOURCE = REPOSITORY / "shared"
OUTPUT = REPOSITORY / "dist" / "asset_validator.zip"


def main() -> None:
    """Package the addon with a generated in-addon copy of shared contracts."""
    with tempfile.TemporaryDirectory() as temporary_directory:
        stage = Path(temporary_directory) / "asset_validator"
        shutil.copytree(
            ADDON_SOURCE,
            stage,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".ruff_cache"),
        )
        shutil.copytree(SHARED_SOURCE, stage / "shared")
        OUTPUT.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in stage.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(stage.parent))
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
