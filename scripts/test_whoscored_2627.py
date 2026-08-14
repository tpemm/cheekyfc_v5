#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe WhoScored 2026/27 through SoccerData."
    )
    parser.add_argument("--season", default="2627")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from football_data.sources.whoscored.probe import run_whoscored_probe

    report = run_whoscored_probe(project_root, season=args.season)
    print(json.dumps(report, indent=2, default=str))
    return 1 if "fatal_error" in report else 0


if __name__ == "__main__":
    raise SystemExit(main())
