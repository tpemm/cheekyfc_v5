#!/usr/bin/env python3
r"""
collect_fantrax_code_for_cleanup.py

Creates a small ZIP containing the current Fantrax project code and configuration
needed for the v1.0 architecture cleanup.

It does NOT include raw/processed datasets.

Output:
    C:\Users\Tommy\fantrax_data\fantrax_code_for_cleanup.zip
"""

from __future__ import annotations

import sys

import json
import zipfile
from datetime import datetime
from pathlib import Path


# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
OUTPUT_ZIP = PROJECT_ROOT / "fantrax_code_for_cleanup.zip"

INCLUDE_DIRS = [
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "app",
]

INCLUDE_ROOT_FILES = [
    PROJECT_ROOT / "requirements.txt",
    PROJECT_ROOT / "run_app.bat",
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / ".streamlit" / "config.toml",
]

EXCLUDE_PARTS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
}

ALLOWED_SUFFIXES = {
    ".py",
    ".bat",
    ".ps1",
    ".toml",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
}


def should_include(path: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in EXCLUDE_PARTS for part in path.parts):
        return False
    return path.suffix.lower() in ALLOWED_SUFFIXES


def main() -> None:
    if not PROJECT_ROOT.exists():
        raise FileNotFoundError(f"Project root not found: {PROJECT_ROOT}")

    files: list[Path] = []

    for folder in INCLUDE_DIRS:
        if not folder.exists():
            print(f"Missing optional folder: {folder}")
            continue
        files.extend(path for path in folder.rglob("*") if should_include(path))

    for path in INCLUDE_ROOT_FILES:
        if path.exists() and should_include(path):
            files.append(path)

    files = sorted(set(files))

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "file_count": len(files),
        "files": [
            {
                "relative_path": str(path.relative_to(PROJECT_ROOT)),
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(
                    path.stat().st_mtime
                ).isoformat(timespec="seconds"),
            }
            for path in files
        ],
    }

    with zipfile.ZipFile(
        OUTPUT_ZIP,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for path in files:
            archive.write(
                path,
                arcname=str(path.relative_to(PROJECT_ROOT)),
            )

        archive.writestr(
            "cleanup_manifest.json",
            json.dumps(manifest, indent=2),
        )

    print("=" * 80)
    print("Fantrax code package created")
    print("=" * 80)
    print(f"Files included: {len(files)}")
    print(f"Output: {OUTPUT_ZIP}")
    print()
    print("Upload fantrax_code_for_cleanup.zip to ChatGPT.")


if __name__ == "__main__":
    main()
