#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault("SOCCERDATA_DIR",str(ROOT/"data/raw/soccerdata/runtime"))
from integrations.whoscored.acquisition import capture_direct_match
p=argparse.ArgumentParser();p.add_argument("--match-id",type=int,required=True);p.add_argument("--timeout",type=int,default=30);a=p.parse_args()
print(json.dumps(capture_direct_match(a.match_id,ROOT/"data/raw/whoscored/2526/poc/match_29140",a.timeout),indent=2))
