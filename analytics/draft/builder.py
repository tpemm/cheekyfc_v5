"""Canonical v5 entry point for the 2026/27 draft dataset builder.

The tested v1.2.2 implementation remains the source of truth during the v5
migration. This wrapper gives future app code one stable import and command.
"""
from __future__ import annotations

import runpy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_BUILDER = PROJECT_ROOT / "scripts" / "build_draft_tool_v1_2_2_2627.py"


def main() -> None:
    if not LEGACY_BUILDER.exists():
        raise FileNotFoundError(f"Draft builder not found: {LEGACY_BUILDER}")
    runpy.run_path(str(LEGACY_BUILDER), run_name="__main__")


if __name__ == "__main__":
    main()
