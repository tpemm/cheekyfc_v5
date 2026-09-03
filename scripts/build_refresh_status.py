#!/usr/bin/env python3
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.services.refresh_status import derive_refresh_status
from integrations.whoscored.workflows import atomic_csv
p=argparse.ArgumentParser();p.add_argument('--season',default='2526');a=p.parse_args();frame=derive_refresh_status(ROOT,a.season);out=ROOT/f'data/quality/season_{a.season}/refresh_status_{a.season}.csv';atomic_csv(frame,out);print(frame.to_string(index=False))
