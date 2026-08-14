from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from football_data.common.export import save_csv, save_json


def flatten(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.index, pd.MultiIndex) or out.index.name is not None:
        out = out.reset_index()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            "__".join(str(x) for x in col if str(x) not in {"", "None"})
            for col in out.columns.to_flat_index()
        ]
    else:
        out.columns = [str(c) for c in out.columns]
    return out


def run_whoscored_probe(project_root: Path, season: str = "2627") -> dict[str, Any]:
    import soccerdata as sd

    raw_dir = project_root / "data" / "raw" / "whoscored"
    reports_dir = project_root / "data" / "reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "source": "WhoScored via SoccerData",
        "season": season,
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "methods": {},
    }

    try:
        reader = sd.WhoScored(
            leagues="ENG-Premier League",
            seasons=season,
            no_cache=True,
            data_dir=raw_dir / "_soccerdata_cache",
        )
    except Exception as exc:
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
        save_json(report, reports_dir / "whoscored_2627_probe.json")
        return report

    try:
        schedule = reader.read_schedule()
        schedule = flatten(schedule)
        save_csv(schedule, raw_dir / "whoscored_schedule_2627.csv")
        report["methods"]["read_schedule"] = {
            "ok": True,
            "rows": int(len(schedule)),
            "columns": list(schedule.columns),
            "preview_count": int(
                schedule["has_preview"].fillna(False).astype(bool).sum()
            ) if "has_preview" in schedule.columns else None,
            "confirmed_lineup_count": int(
                schedule["is_lineup_confirmed"].fillna(False).astype(bool).sum()
            ) if "is_lineup_confirmed" in schedule.columns else None,
        }
    except Exception as exc:
        report["methods"]["read_schedule"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    report["note"] = (
        "WhoScored is best used for schedule, match previews, missing players, "
        "confirmed lineups and event data. Missing-player calls require a "
        "specific match_id and become useful close to each fixture."
    )
    save_json(report, reports_dir / "whoscored_2627_probe.json")
    return report
