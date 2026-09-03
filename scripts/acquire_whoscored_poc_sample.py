#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault("SOCCERDATA_DIR",str(ROOT/"data/raw/soccerdata/runtime"))
from integrations.whoscored.acquisition import capture_direct_matches
p=argparse.ArgumentParser();p.add_argument("--remaining",action="store_true");p.add_argument("--timeout",type=int,default=30);a=p.parse_args()
m=pd.read_csv(ROOT/"data/reference/advanced_match_poc_sample_2526.csv")
if a.remaining: m=m[m.understat_match_id.ne(29140)]
items=m[["canonical_match_id","understat_match_id","whoscored_match_id","date","home_club_id","away_club_id"]].to_dict("records")
results=capture_direct_matches(items,ROOT/"data/raw/whoscored/2526/poc",a.timeout)
print(json.dumps(results,indent=2));raise SystemExit(1 if any(x["status"]=="error" for x in results) else 0)
