"""Refresh proven Fantrax sources into the validated 2026/27 raw cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fantrax.live.acquisition import fetch_json, validate_api_payload
from fantrax.live.cache import cache_path, refresh_json
from fantrax.live.config import load_live_season_config
from fantrax.live.normalization import load_cached_json
from fantrax.live.pipeline import _explicit_period
from fantrax.live.weekly_acquisition import refresh_weekly_stats
from fantrax.utils.cli import configure_unicode_console


SUPPORTED = ("league_metadata", "standings", "rosters", "weekly_stats")


def roster_periods(config, *, explicit=None, full_history=False, league_payload=None):
    if explicit:
        return (config.validate_period(explicit),)
    if full_history:
        return tuple(range(config.period_minimum, config.period_maximum + 1))
    current = _explicit_period(league_payload) if league_payload else None
    return (config.validate_period(current or config.period_minimum),)


def _stdin_parameters() -> dict:
    if sys.stdin.isatty(): return {}
    text=sys.stdin.read().strip()
    return json.loads(text) if text else {}


def main() -> int:
    configure_unicode_console()
    stage="configuration"
    try:
        parser=argparse.ArgumentParser(); parser.add_argument("--source",choices=(*SUPPORTED,"all"),default=None); parser.add_argument("--period",type=int,default=None); parser.add_argument("--full-history",action="store_true"); parser.add_argument("--weekly-mode",choices=("normal","backfill","force_current"),default=None); parser.add_argument("--force",action="store_true")
        args=parser.parse_args(); supplied=_stdin_parameters(); source=args.source or supplied.get("source","all"); config=load_live_season_config(); league_id=config.require_league_id()
        print(f"REFRESH_CONTEXT season_id={config.season_id} league_id={league_id} script={Path(__file__).resolve()}")
    except Exception as exc:
        print(f"REFRESH_FAILURE stage={stage} exception_type={type(exc).__name__} message={exc}",file=sys.stderr); return 1
    period=args.period or supplied.get("period"); full_history=args.full_history or bool(supplied.get("full_history",False))
    sources=("league_metadata","standings","rosters","weekly_stats") if source=="all" else (source,)
    results=[]
    try:
      for item in sources:
        if item=="weekly_stats":
            stage="weekly_player_stats"
            league_path=cache_path(config,"league","league_metadata")
            if not league_path.exists(): raise FileNotFoundError("Weekly acquisition requires cached league metadata")
            weekly_mode=args.weekly_mode or supplied.get("weekly_mode","normal"); force=args.force or bool(supplied.get("force",False))
            weekly=refresh_weekly_stats(load_cached_json(league_path),league_id=league_id,raw_root=config.raw_root,project_root=PROJECT_ROOT,mode=weekly_mode,period=period,force=force)
            print(f"WEEKLY_STATS_STATUS status={weekly['status']} current_period={weekly['current_period']} targets={weekly['targets']}")
            results.append({"source":item,**weekly})
        elif item=="rosters":
            stage="getTeamRosters"
            if period:
                periods=roster_periods(config,explicit=period)
            elif full_history:
                periods=roster_periods(config,full_history=True)
            else:
                league_path=cache_path(config,"league","league_metadata")
                league_payload=load_cached_json(league_path) if league_path.exists() else None
                periods=roster_periods(config,league_payload=league_payload)
            for value in periods:
                path=cache_path(config,"rosters","rosters",period=value)
                metadata=refresh_json(path,lambda value=value:fetch_json("rosters",league_id,period=value),config=config,request_type="rosters",source="Fantrax getTeamRosters",validator=validate_api_payload)
                results.append({"source":item,"period":value,"path":str(path),"retrieved_at":metadata["retrieved_at"]})
        else:
            stage="getLeagueInfo" if item=="league_metadata" else "getStandings"
            category="league" if item=="league_metadata" else "standings"; path=cache_path(config,category,item)
            metadata=refresh_json(path,lambda item=item:fetch_json(item,league_id),config=config,request_type=item,source=f"Fantrax {item}",validator=validate_api_payload)
            results.append({"source":item,"path":str(path),"retrieved_at":metadata["retrieved_at"]})
      print(json.dumps({"season_id":config.season_id,"league_id":league_id,"refreshed":results},indent=2)); return 0
    except Exception as exc:
      status=getattr(exc,"code",None)
      guidance=" Fantrax denied access; verify league visibility or provide the supported authenticated credential." if status in {401,403} else ""
      print(f"REFRESH_FAILURE stage={stage} season_id={config.season_id} league_id={league_id} exception_type={type(exc).__name__} message={exc}.{guidance}",file=sys.stderr)
      return 1


if __name__=="__main__": raise SystemExit(main())
