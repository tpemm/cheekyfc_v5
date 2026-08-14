from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from config.project_paths import PROJECT_ROOT

COMMANDS = {
    "refresh": PROJECT_ROOT / "fantrax" / "refresh" / "refresh_all_fantrax_data.py",
    "analytics": None,
    "finalize": PROJECT_ROOT / "fantrax" / "finalize" / "finalize_fantrax_season_2526.py",
}
ANALYTICS = [
    PROJECT_ROOT / "fantrax" / "analytics" / "build_league_awards_views.py",
    PROJECT_ROOT / "fantrax" / "analytics" / "build_efficiency_ghost_awards_views.py",
]

def run(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    result = subprocess.run([sys.executable, str(path)], cwd=PROJECT_ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)

def main() -> None:
    parser = argparse.ArgumentParser(description="Fantrax Data command center")
    parser.add_argument("command", choices=["app", "refresh", "analytics", "finalize"])
    args = parser.parse_args()
    if args.command == "app":
        raise SystemExit(subprocess.run([sys.executable, "-m", "streamlit", "run", str(PROJECT_ROOT / "app" / "fantrax_data_app.py")], cwd=PROJECT_ROOT).returncode)
    if args.command == "analytics":
        for script in ANALYTICS:
            run(script)
        return
    run(COMMANDS[args.command])

if __name__ == "__main__":
    main()
