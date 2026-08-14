"""Build and validate normalized live-season datasets from raw cache only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT=Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0,str(PROJECT_ROOT))
from fantrax.live.pipeline import build_live_season
from fantrax.utils.cli import configure_unicode_console


def main() -> int:
    configure_unicode_console()
    stage="normalization"
    try:
        print(f"BUILD_CONTEXT season_id=2627 script={Path(__file__).resolve()}")
        result=build_live_season()
    except Exception as exc:
        print(f"BUILD_FAILURE stage={stage} season_id=2627 exception_type={type(exc).__name__} message={exc}",file=sys.stderr)
        return 1
    print(json.dumps({"manifest":str(result["manifest_path"]),"datasets":result["quality"].to_dict("records"),"unresolved":len(result["unresolved"])},indent=2))
    return 0


if __name__=="__main__": raise SystemExit(main())
