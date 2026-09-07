#!/usr/bin/env python3
"""The single commissioner-desktop command for the weekly refresh."""
from __future__ import annotations
import argparse, importlib.util, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.services.machine_role import MachineRoleError, require_commissioner_writer
from core.services.smart_refresh import build_smart_refresh_plan
from core.services.refresh_publisher import publish_refresh
from integrations.whoscored.workflows import atomic_json


def _run(script: str, *args: object) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], cwd=ROOT, check=False).returncode


def desktop_dependencies() -> list[str]:
    return [name for name in ("soccerdata", "playwright") if importlib.util.find_spec(name) is None]


def provider_statuses(report: dict) -> dict[str, str]:
    """Evaluate each provider's required stages, never another provider's failure."""
    stages={item["stage"]:item["returncode"] for item in report.get("stages",[])}
    required={"Fantrax":("fantrax_weekly","fantrax_matchups","core_build","unified_models","correction_and_identity_reconciliation"),
              "WhoScored":("whoscored_advanced",), "Understat":("understat_acquisition","understat_products")}
    result={}
    for provider,names in required.items():
        codes=[stages.get(name) for name in names]
        result[provider]="PASS" if all(code==0 for code in codes) else "PARTIAL" if any(code==0 for code in codes) else "FAIL"
    final=report.get("final_plan",{})
    for provider,key in (("WhoScored","whoscored"),("Understat","understat")):
        state=final.get(key,{})
        missing=state.get("missing_matches",0) if key=="understat" else state.get("missing_eligible",0)+state.get("failed_retryable",0)
        if result[provider]=="PASS" and missing:
            result[provider]="PARTIAL"
    return result


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
    missing=desktop_dependencies()
    if missing:
        print(f"DESKTOP REFRESH FAIL: missing desktop dependencies: {', '.join(missing)}")
        print(f'Install with: "{sys.executable}" -m pip install -r requirements-desktop.txt')
        print("Do not run SMART REFRESH yet.")
        return 2
    if _run("authenticate_fantrax_desktop.py", "--validate-only", "--period", period):
        print("DESKTOP REFRESH FAIL\nFantrax: FAIL (authentication is missing or stale)\nDo not run SMART REFRESH yet.", file=sys.stderr)
        return 2
    report_path=ROOT/f"data/quality/season_{args.season}/weekly_commissioner_refresh_latest.json"
    before=report_path.read_bytes() if report_path.exists() else None
    refresh = _run("weekly_commissioner_refresh.py", "--season", args.season, "--period", period)
    report={}
    if report_path.exists() and report_path.read_bytes()!=before:
        try:report=json.loads(report_path.read_text(encoding="utf-8"))
        except (ValueError,OSError):pass
    statuses=provider_statuses(report)
    protected = getattr(initial, "previous_gw_status", "") == "FINALIZED"
    previous_check = _run("build_current_data_integrity.py", "--season", args.season, "--period", initial.previous_gw) if initial.previous_gw and not protected else 0
    failed = refresh or previous_check or any(value not in {"PASS","CACHE_HIT","NO_ACTION_REQUIRED"} for value in statuses.values())
    atomic_json({"season":args.season,"current_gw":period,"previous_gw":initial.previous_gw,"previous_correction_check":"PASS" if not previous_check else "FAIL"},ROOT/f"data/quality/season_{args.season}/desktop_source_refresh_latest.json")
    final = build_smart_refresh_plan(args.season)
    publish = publish_refresh(ROOT, season=args.season, current_gw=initial.current_gw,
                              refresh_status="PASS" if not failed else "FAIL")
    print(f"\n{'DESKTOP REFRESH COMPLETE' if not failed else 'DESKTOP REFRESH PARTIAL'}")
    for provider,status in statuses.items():print(f"{provider}: {status}")
    print(f"Current GW: {initial.current_gw}")
    if initial.previous_gw: print(f"GW{initial.previous_gw} correction check: {'FINALIZED_PROTECTED' if protected else ('PASS' if not previous_check else 'FAIL')}")
    print_publish(publish, refresh_succeeded=not failed)
    return 0 if not failed and publish.status != "BLOCKED" else 2


def print_publish(result, *, refresh_succeeded: bool = False) -> None:
    print(f"Publish eligibility: {result.status}")
    print(f"Approved changed files: {len(result.files)}")
    for reason in result.blockers:
        print(f"  {reason}")
    if result.commit:
        print(f"Commit: {result.commit}")
    if refresh_succeeded and result.status in {"PUBLISHED","NO_ACTION_REQUIRED"}:
        print("\nOpen the Streamlit app and click SMART REFRESH.")
    else:
        print("\nDo not run SMART REFRESH yet.")


if __name__ == "__main__":
    raise SystemExit(main())
