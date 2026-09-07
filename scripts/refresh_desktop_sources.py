#!/usr/bin/env python3
"""The single commissioner-desktop command for the weekly refresh."""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.services.machine_role import MachineRoleError, require_commissioner_writer
from core.services.smart_refresh import build_smart_refresh_plan
from core.services.refresh_publisher import publish_refresh
from integrations.whoscored.workflows import atomic_json


def _run(script: str, *args: object) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2627")
    parser.add_argument("--publish-dry-run", action="store_true",
                        help="Inspect publish eligibility only; no acquisition, rebuild, staging, commit or push")
    args = parser.parse_args()
    try:
        require_commissioner_writer("desktop source refresh")
    except MachineRoleError as exc:
        print(f"DESKTOP REFRESH FAIL\n{exc}", file=sys.stderr)
        return 2
    initial = build_smart_refresh_plan(args.season)
    period = initial.current_gw or 1
    if args.publish_dry_run:
        result = publish_refresh(ROOT, season=args.season, current_gw=initial.current_gw,
                                 refresh_status="NOT_RUN", dry_run=True)
        print("Refresh: NOT_RUN (publish validation only)")
        for name in ("fantrax", "whoscored", "understat"):
            print(f"{name.title()}: {getattr(initial, name).status}")
        print(f"Current GW: {initial.current_gw}")
        print(f"Previous GW correction check: {initial.previous_gw_status}; {'REQUIRED' if initial.correction_check_required else 'NOT_REQUIRED_OR_RECORDED_PASS'}")
        print_publish(result)
        return 2 if result.status == "BLOCKED" else 0
    if _run("authenticate_fantrax_desktop.py", "--validate-only", "--period", period):
        print("DESKTOP REFRESH FAIL\nFantrax: FAIL (authentication is missing or stale)", file=sys.stderr)
        return 2
    refresh = _run("weekly_commissioner_refresh.py", "--season", args.season, "--period", period)
    protected = getattr(initial, "previous_gw_status", "") == "FINALIZED"
    previous_check = _run("build_current_data_integrity.py", "--season", args.season, "--period", initial.previous_gw) if initial.previous_gw and not protected else 0
    failed = refresh or previous_check
    atomic_json({"season":args.season,"current_gw":period,"previous_gw":initial.previous_gw,"previous_correction_check":"PASS" if not previous_check else "FAIL"},ROOT/f"data/quality/season_{args.season}/desktop_source_refresh_latest.json")
    final = build_smart_refresh_plan(args.season)
    publish = publish_refresh(ROOT, season=args.season, current_gw=initial.current_gw,
                              refresh_status="PASS" if not failed else "FAIL")
    print(f"\n{'DESKTOP REFRESH COMPLETE' if not failed else 'DESKTOP REFRESH PARTIAL'}")
    print(f"Fantrax: {'PASS' if not refresh else 'FAIL'}")
    print(f"WhoScored: {'CACHE_HIT' if final.whoscored.status == 'CACHE_HIT' else ('PASS' if not refresh else 'PARTIAL')}")
    print(f"Understat: {'CACHE_HIT' if final.understat.status == 'CACHE_HIT' else ('PASS' if not refresh else 'PARTIAL')}")
    print(f"Current GW: {initial.current_gw}")
    if initial.previous_gw: print(f"GW{initial.previous_gw} correction check: {'FINALIZED_PROTECTED' if protected else ('PASS' if not previous_check else 'FAIL')}")
    print_publish(publish)
    return 0 if not failed and publish.status != "BLOCKED" else 2


def print_publish(result) -> None:
    print(f"Publish eligibility: {result.status}")
    print(f"Approved changed files: {len(result.files)}")
    for reason in result.blockers:
        print(f"  {reason}")
    if result.commit:
        print(f"Commit: {result.commit}")
    print("\nOpen the Streamlit app and click SMART REFRESH.")


if __name__ == "__main__":
    raise SystemExit(main())
