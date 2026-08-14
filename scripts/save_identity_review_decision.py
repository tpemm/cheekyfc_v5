"""Validate and persist one identity-review decision from approved stdin."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from analytics.player_registry.review import (
    DECISION_COLUMNS,
    apply_decisions_to_review,
    save_review_decision,
)
from core.models.data_result import DataStatus
from core.services.data_manager import DataManager


def main() -> None:
    started = time.perf_counter()
    parameters = json.loads(sys.stdin.read())
    season_id = str(parameters.pop("season_id", "2627"))
    data = DataManager()
    review = data.load_frame(
        "player_identity_review", season_id, "working"
    ).data
    result = data.load_frame(
        "player_alias_overrides", season_id, "working"
    )
    decisions = (
        result.data.copy()
        if result.status not in {DataStatus.MISSING, DataStatus.EMPTY}
        else pd.DataFrame(columns=DECISION_COLUMNS)
    )
    loaded_at = time.perf_counter()
    updated = save_review_decision(
        decisions, review, season_id=season_id, **parameters
    )
    validated_at = time.perf_counter()
    output = data.resolve_path(
        "player_alias_overrides", season_id, "working"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(output, index=False, encoding="utf-8-sig")
    decision_written_at = time.perf_counter()
    synchronized_review = apply_decisions_to_review(review, updated)
    review_output = data.resolve_path(
        "player_identity_review", season_id, "working"
    )
    synchronized_review.to_csv(review_output, index=False, encoding="utf-8-sig")
    finished = time.perf_counter()
    print(
        f"Saved {parameters['decision']} identity-review decision and "
        f"synchronized {len(synchronized_review)} review rows."
    )
    print(
        "Timing: "
        f"load={loaded_at - started:.3f}s; "
        f"validate={validated_at - loaded_at:.3f}s; "
        f"decision_write={decision_written_at - validated_at:.3f}s; "
        f"review_sync_write={finished - decision_written_at:.3f}s; "
        f"total={finished - started:.3f}s"
    )


if __name__ == "__main__":
    main()
