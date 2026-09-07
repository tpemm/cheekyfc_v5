#!/usr/bin/env python3
"""Rebuild current products from existing valid caches; never acquire providers."""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.services.smart_refresh import build_smart_refresh_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2627")
    args = parser.parse_args()
    plan = build_smart_refresh_plan(args.season)
    if plan.desktop_acquisition_required:
        print("DESKTOP_REQUIRED: provider caches must be refreshed before dependent products are rebuilt.")
        return 2
    commands = [
        ("core", "build_live_season.py", ()),
        ("understat", "build_understat_live_products.py", ()),
        ("whoscored", "build_whoscored_live_products.py", ("--season", args.season)),
        ("participation", "build_current_player_participation.py", ("--season", args.season)),
        ("weekly", "build_live_weekly_unified.py", ("--season", args.season)),
        ("teams", "build_team_analytics_2627.py", ("--season", args.season)),
        ("tactical", "build_team_tactical_99c.py", ("--season", args.season)),
    ]
    for label, script, extra in commands:
        done = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *extra], cwd=ROOT, check=False)
        if done.returncode:
            print(f"BUILD_FAILURE stage={label}")
            return done.returncode
    print("REFRESH COMPLETE: cached canonical, League Hub, player, team, Fantasy Allowed, and tactical products updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
