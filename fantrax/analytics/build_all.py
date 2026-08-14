#!/usr/bin/env python3
"""Run the stable Fantrax analytics builders in dependency order."""
from __future__ import annotations
import argparse
import subprocess
import sys

from fantrax.utils.cli import configure_unicode_console

ANALYTICS_MODULES = (
    "fantrax.analytics.manager.build_efficiency_ghost_awards_views",
    "fantrax.analytics.team.build_league_awards_views",
    "fantrax.analytics.manager.build_decision_views",
    "fantrax.analytics.player.build_player_views",
)

def run_module(module: str) -> None:
    print(f"\n=== {module} ===")
    subprocess.run([sys.executable, "-m", module], check=True)

def main() -> None:
    configure_unicode_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-master", action="store_true", help="Rebuild processed master tables before analytics views.")
    args = parser.parse_args()
    if args.rebuild_master:
        run_module("fantrax.analytics.core.build_master_weekly")
    for module in ANALYTICS_MODULES:
        run_module(module)
    print("\nAll analytics builders completed successfully.")

if __name__ == "__main__":
    main()
