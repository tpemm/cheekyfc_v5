#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from integrations.whoscored.workflows import atomic_csv,build_season_manifest
p=argparse.ArgumentParser();p.add_argument('--season',default='2526');a=p.parse_args()
frame=build_season_manifest(ROOT,a.season);out=ROOT/f'data/reference/whoscored_season_manifest_{a.season}.csv';atomic_csv(frame,out)
print(json.dumps({'season':a.season,'matches':len(frame),'completed':int(frame.is_completed.sum()),'resolved':int(frame.resolution_status.eq('RESOLVED').sum()),'output':str(out)}))
