from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
CONFIG_DIR = PROJECT_ROOT / "config"
PACKAGE_DIR = PROJECT_ROOT / "fantrax"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = PROJECT_ROOT / "raw_data"
PROCESSED_DATA_DIR = PROJECT_ROOT / "processed_data"
REPORTS_DIR = PROJECT_ROOT / "reports"
ACTIVE_RAW_DIR = DATA_DIR / "raw"
ACTIVE_PROCESSED_DIR = DATA_DIR / "processed"
ACTIVE_ANALYTICS_DIR = DATA_DIR / "analytics_views"
REFERENCE_DIR = DATA_DIR / "reference"
FANTRAX_API_RAW_DIR = RAW_DATA_DIR / "fantrax_api"
FANTRAX_API_DIR = PROCESSED_DATA_DIR / "fantrax_api"
SEASONS_DIR = DATA_DIR / "seasons"
SEASONS_CONFIG = CONFIG_DIR / "seasons.json"

def load_seasons() -> dict[str, dict[str, Any]]:
    return json.loads(SEASONS_CONFIG.read_text(encoding="utf-8"))

def active_season_id() -> str:
    seasons = load_seasons()
    active = [sid for sid, cfg in seasons.items() if cfg.get("status") == "active"]
    if len(active) == 1:
        return active[0]
    configured = [sid for sid, cfg in seasons.items() if cfg.get("enabled") and sid != "all_time"]
    if configured:
        return configured[-1]
    raise RuntimeError("No enabled season is configured in config/seasons.json")

def season_dir(season_id: str) -> Path:
    return SEASONS_DIR / season_id

def season_processed_dir(season_id: str) -> Path:
    return season_dir(season_id) / "processed"

def season_analytics_dir(season_id: str) -> Path:
    return season_dir(season_id) / "analytics_views"

def season_reference_dir(season_id: str) -> Path:
    return season_dir(season_id) / "reference"

def season_reports_dir(season_id: str) -> Path:
    return season_dir(season_id) / "reports"
