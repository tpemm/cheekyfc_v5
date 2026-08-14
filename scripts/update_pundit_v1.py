#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update Fantasy Football Pundit data."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Download fresh copies instead of using local HTML snapshots.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from football_data.sources.pundit.run import run_pundit_update

    summary = run_pundit_update(project_root, force=args.force)
    print(json.dumps(summary, indent=2, default=str))

    warnings = summary.get("lineups", {}).get("warnings", [])
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
