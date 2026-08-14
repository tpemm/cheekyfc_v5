"""Generate the registered Player Identity Review artifact."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from analytics.player_registry.review import build_identity_review
from core.models.data_result import DataStatus
from core.services.data_manager import DataManager


def _optional_frame(data: DataManager, key: str, season_id: str) -> pd.DataFrame:
    result = data.load_frame(key, season_id, "working")
    if result.status in {DataStatus.MISSING, DataStatus.EMPTY}:
        return pd.DataFrame()
    return result.data.copy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season-id", default="2627")
    args = parser.parse_args()
    data = DataManager()
    registry = data.load_frame(
        "player_registry", args.season_id, "working"
    ).data
    current = data.load_frame(
        "current_squad_snapshot", args.season_id, "working"
    ).data
    draft = _optional_frame(data, "draft_rankings", args.season_id)
    decisions = _optional_frame(data, "player_alias_overrides", args.season_id)
    review = build_identity_review(
        registry, current, draft, decisions, season_id=args.season_id
    )
    output = data.resolve_path(
        "player_identity_review", args.season_id, "working"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    review.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"Generated {len(review)} identity-review rows at {output}")


if __name__ == "__main__":
    main()
