from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from football_data.common.export import save_csv, save_json
from football_data.sources.pundit.parser import (
    parse_fixture_page,
    parse_predicted_lineups,
)
from football_data.sources.pundit.scraper import scrape_pages


def run_pundit_update(
    project_root: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    raw_dir = project_root / "data" / "raw" / "pundit"
    processed_dir = project_root / "data" / "processed"
    reports_dir = project_root / "data" / "reports"
    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    inventory = scrape_pages(raw_dir, force=force)
    save_json(inventory, reports_dir / "pundit_page_inventory.json")

    players, teams, lineup_summary = parse_predicted_lineups(
        raw_dir / "predicted_lineups.html"
    )
    save_csv(players, processed_dir / "pundit_predicted_lineups.csv")
    save_csv(teams, processed_dir / "pundit_team_lineup_summary.csv")

    fixture_candidates = [raw_dir / "fixture_analysis.html"]
    fixture_candidates.extend(
        sorted(raw_dir.glob("fixture_analysis_iframe_*.html"))
    )

    fixture_df = pd.DataFrame()
    fixture_summary: dict[str, Any] = {}
    fixture_source = None

    for candidate in fixture_candidates:
        parsed, summary = parse_fixture_page(candidate)
        if not parsed.empty:
            fixture_df = parsed
            fixture_summary = summary
            fixture_source = str(candidate)
            break
        fixture_summary = summary

    save_csv(fixture_df, processed_dir / "pundit_fixture_difficulty_raw.csv")

    summary = {
        "source": "Fantasy Football Pundit",
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "force_download": force,
        "lineups": lineup_summary,
        "fixtures": {
            **fixture_summary,
            "source_file": fixture_source,
        },
        "outputs": {
            "predicted_lineups": str(
                processed_dir / "pundit_predicted_lineups.csv"
            ),
            "team_lineup_summary": str(
                processed_dir / "pundit_team_lineup_summary.csv"
            ),
            "fixture_difficulty_raw": str(
                processed_dir / "pundit_fixture_difficulty_raw.csv"
            ),
            "page_inventory": str(
                reports_dir / "pundit_page_inventory.json"
            ),
        },
    }
    save_json(summary, reports_dir / "pundit_scrape_summary.json")
    return summary
