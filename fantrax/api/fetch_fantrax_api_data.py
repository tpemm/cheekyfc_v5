#!/usr/bin/env python3
"""
fetch_fantrax_api_data.py

Purpose
-------
Download raw Fantrax API JSON for league-level analytics:
- league info
- standings
- team rosters by scoring period

This script is intentionally "raw-first":
1. Fetch JSON from Fantrax API endpoints.
2. Save the raw API responses under raw_data/fantrax_api/.
3. Print top-level JSON keys/structure so we can safely map them into CSVs later.

Current league:
    rg1i70pfmdhjhvn3

Recommended location:
    scripts/fetch_fantrax_api_data.py

Run from project root:
    python scripts/fetch_fantrax_api_data.py

Optional:
    python scripts/fetch_fantrax_api_data.py --league-id rg1i70pfmdhjhvn3
    python scripts/fetch_fantrax_api_data.py --periods 1-27
    python scripts/fetch_fantrax_api_data.py --force
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_LEAGUE_ID = "rg1i70pfmdhjhvn3"
BASE_URL = "https://www.fantrax.com/fxea/general"

# Edit this if your project root is different.
# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
from fantrax.utils.cli import configure_unicode_console

RAW_API_DIR = PROJECT_ROOT / "raw_data" / "fantrax_api"
ROSTERS_DIR = RAW_API_DIR / "rosters"


def parse_periods(periods_text: str | None) -> list[int]:
    """
    Parse period input like:
        "1-27"
        "1,2,3"
        "1-5,8,10-12"

    If omitted, defaults to 1-38, which is safe for EPL-style seasons.
    Missing/future periods may still return JSON depending on Fantrax.
    """
    if not periods_text:
        return list(range(1, 39))

    periods: set[int] = set()
    chunks = [chunk.strip() for chunk in periods_text.split(",") if chunk.strip()]

    for chunk in chunks:
        if "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            periods.update(range(start, end + 1))
        else:
            periods.add(int(chunk))

    return sorted(periods)


def request_json(endpoint: str, params: dict[str, Any], timeout: int = 30) -> Any:
    """
    Fetch JSON from a Fantrax API endpoint.
    """
    url = f"{BASE_URL}/{endpoint}?{urlencode(params)}"
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 FantraxAnalyticsProject/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )

    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error for {url}: {exc.code} {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error for {url}: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        snippet = raw[:500].replace("\n", " ")
        raise RuntimeError(f"Response was not valid JSON for {url}. Start of response: {snippet}") from exc


def save_json(path: Path, data: Any, force: bool = False) -> None:
    """
    Save JSON to disk. Skip existing files unless force=True.
    """
    if path.exists() and not force:
        print(f"SKIP existing: {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"SAVED: {path}")


def short_type(value: Any) -> str:
    if isinstance(value, dict):
        return f"dict[{len(value)}]"
    if isinstance(value, list):
        return f"list[{len(value)}]"
    return type(value).__name__


def print_json_shape(label: str, data: Any, max_depth: int = 3, max_items: int = 12) -> None:
    """
    Print a compact structure summary without dumping full data.
    """
    print("\n" + "=" * 80)
    print(f"JSON SHAPE: {label}")
    print("=" * 80)

    def walk(obj: Any, prefix: str = "", depth: int = 0) -> None:
        if depth > max_depth:
            return

        if isinstance(obj, dict):
            items = list(obj.items())
            for key, value in items[:max_items]:
                print(f"{prefix}{key}: {short_type(value)}")
                if isinstance(value, (dict, list)):
                    walk(value, prefix + "  ", depth + 1)
            if len(items) > max_items:
                print(f"{prefix}... ({len(items) - max_items} more keys)")

        elif isinstance(obj, list):
            print(f"{prefix}[list length: {len(obj)}]")
            if obj:
                print(f"{prefix}[0]: {short_type(obj[0])}")
                walk(obj[0], prefix + "  ", depth + 1)

        else:
            print(f"{prefix}{repr(obj)[:120]}")

    walk(data)


def extract_likely_scoring_periods(league_info: Any) -> list[int]:
    """
    Best-effort helper to discover periods from league_info.

    Fantrax JSON shape can vary, so this searches recursively for keys that look
    like scoring periods or periods and extracts integer period numbers.

    If no periods are found, caller should use the user-specified/default period range.
    """
    found: set[int] = set()

    period_key_pattern = re.compile(r"(scoring.*period|period)", re.IGNORECASE)

    def visit(obj: Any, parent_key: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_text = str(key)

                # Keys like "1", "2", etc under a scoring period object
                if parent_key and period_key_pattern.search(parent_key):
                    if key_text.isdigit():
                        found.add(int(key_text))

                # Values with period-like fields
                if period_key_pattern.search(key_text):
                    if isinstance(value, int):
                        found.add(value)
                    elif isinstance(value, str) and value.isdigit():
                        found.add(int(value))
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, int):
                                found.add(item)
                            elif isinstance(item, str) and item.isdigit():
                                found.add(int(item))
                            elif isinstance(item, dict):
                                for candidate_key in ("period", "periodNumber", "scoringPeriod", "scoringPeriodId", "number"):
                                    candidate_value = item.get(candidate_key)
                                    if isinstance(candidate_value, int):
                                        found.add(candidate_value)
                                    elif isinstance(candidate_value, str) and candidate_value.isdigit():
                                        found.add(int(candidate_value))

                visit(value, key_text)

        elif isinstance(obj, list):
            for item in obj:
                visit(item, parent_key)

    visit(league_info)

    # Keep sane fantasy soccer range. This avoids weird IDs accidentally found.
    return sorted(p for p in found if 1 <= p <= 60)


def main() -> int:
    configure_unicode_console()
    parser = argparse.ArgumentParser(description="Fetch raw Fantrax API data for analytics.")
    parser.add_argument("--league-id", default=DEFAULT_LEAGUE_ID, help="Fantrax league ID.")
    parser.add_argument(
        "--periods",
        default=None,
        help='Scoring periods to fetch, e.g. "1-27" or "1,2,3". Defaults to 1-38 unless discovered.',
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing saved JSON files.")
    parser.add_argument("--sleep", type=float, default=0.4, help="Delay between API requests.")
    args = parser.parse_args()

    league_id = args.league_id

    RAW_API_DIR.mkdir(parents=True, exist_ok=True)
    ROSTERS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nFantrax API Raw Fetch")
    print(f"League ID: {league_id}")
    print(f"Raw output dir: {RAW_API_DIR}")
    print(f"Started: {datetime.now().isoformat(timespec='seconds')}")

    # 1. League info
    league_info = request_json("getLeagueInfo", {"leagueId": league_id})
    save_json(RAW_API_DIR / "league_info.json", league_info, force=args.force)
    print_json_shape("league_info", league_info)

    # 2. Standings
    standings = request_json("getStandings", {"leagueId": league_id})
    save_json(RAW_API_DIR / "standings.json", standings, force=args.force)
    print_json_shape("standings", standings)

    # 3. Try to discover scoring periods from league_info. Fall back to args/default.
    discovered_periods = extract_likely_scoring_periods(league_info)
    requested_periods = parse_periods(args.periods)

    if args.periods:
        periods = requested_periods
        print(f"\nUsing periods from --periods: {periods}")
    elif discovered_periods:
        periods = discovered_periods
        print(f"\nDiscovered likely scoring periods from league_info: {periods}")
    else:
        periods = requested_periods
        print(f"\nCould not discover scoring periods; defaulting to: {periods[0]}-{periods[-1]}")

    # Save a simple period list so later scripts know what was fetched.
    save_json(RAW_API_DIR / "periods_to_fetch.json", {"periods": periods}, force=True)

   # 4. Team rosters by period
    roster_success = 0
    roster_failures: list[tuple[int, str]] = []

    # Always refresh the newest 3 periods.
    # Older periods stay locked unless --force is used.
    rolling_refresh_periods = set(periods[-3:])

    print(f"\nRolling API roster refresh periods: {sorted(rolling_refresh_periods)}")

    for period in periods:
        try:
            data = request_json(
                "getTeamRosters",
                {"leagueId": league_id, "period": period}
            )

            force_this_period = args.force or period in rolling_refresh_periods

            save_json(
                ROSTERS_DIR / f"period_{period:02d}.json",
                data,
                force=force_this_period,
            )

            if roster_success == 0:
                print_json_shape(f"rosters period {period}", data)

            roster_success += 1

        except Exception as exc:
            roster_failures.append((period, str(exc)))
            print(f"FAILED roster period {period}: {exc}")

        time.sleep(args.sleep)

    # 5. Fetch manifest
    manifest = {
        "league_id": league_id,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "endpoints": {
            "league_info": "getLeagueInfo",
            "standings": "getStandings",
            "team_rosters": "getTeamRosters",
        },
        "periods_attempted": periods,
        "roster_success_count": roster_success,
        "roster_failures": [{"period": p, "error": err} for p, err in roster_failures],
        "notes": [
            "This is raw API capture only.",
            "Next step is to create transform_fantrax_api_json.py to flatten JSON into CSV tables.",
            "Keep Fantrax CSVs as the source for detailed player stat-category scoring.",
        ],
    }
    save_json(RAW_API_DIR / "fetch_manifest.json", manifest, force=True)

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)
    print(f"League info: {RAW_API_DIR / 'league_info.json'}")
    print(f"Standings:   {RAW_API_DIR / 'standings.json'}")
    print(f"Rosters:     {ROSTERS_DIR}")
    print(f"Manifest:    {RAW_API_DIR / 'fetch_manifest.json'}")

    if roster_failures:
        print("\nRoster failures:")
        for period, error in roster_failures:
            print(f"  Period {period}: {error}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
