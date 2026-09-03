#!/usr/bin/env python3
"""Revalidate and rebuild normalized Fantrax matchup products from local cache."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fantrax.live.config import load_live_season_config
from fantrax.live.matchup_acquisition import commit_live_scoring

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--period", type=int, default=1);parser.add_argument("--all-cached-model-only",action="store_true"); args = parser.parse_args()
    config = load_live_season_config(); path = config.raw_root / "matchups" / f"period_{args.period:02d}" / "live_scoring.json"
    if args.all_cached_model_only:
        matchup_parts=[];player_parts=[]
        for folder in sorted((config.raw_root/"matchups").glob("period_*")):
            match_path=folder/"fantrax_matchups.csv";player_path=folder/"fantrax_live_player_scoring.csv"
            if match_path.exists():matchup_parts.append(pd.read_csv(match_path))
            if player_path.exists():player_parts.append(pd.read_csv(player_path))
        if not matchup_parts:raise SystemExit("no cached matchup products")
        pd.concat(matchup_parts,ignore_index=True).sort_values(["period","matchup_id"],kind="stable").to_csv(config.model_root/f"fantrax_matchups_{config.season_id}.csv",index=False)
        if player_parts:pd.concat(player_parts,ignore_index=True).sort_values(["period","fantrax_team_id","fantrax_player_id"],kind="stable").to_csv(config.model_root/f"fantrax_live_player_scoring_{config.season_id}.csv",index=False)
        print(json.dumps({"status":"REBUILT_MODEL_FROM_IMMUTABLE_CACHE","periods":len(matchup_parts),"matchups":sum(map(len,matchup_parts)),"player_rows":sum(map(len,player_parts))},indent=2));return 0
    result = commit_live_scoring(json.loads(path.read_text(encoding="utf-8")), raw_root=config.raw_root, model_root=config.model_root, season_id=config.season_id, period=args.period)
    print(json.dumps(result, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
