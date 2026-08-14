from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from integrations.footballdata_client import (
    FootballDataClient,
    FootballDataError,
    load_json,
    pagination_total_pages,
    save_json,
)


CURRENT_SEASON_ID = 103535
CURRENT_EPL_LEAGUE_ID = 15
HISTORICAL_EPL_SEASON_ID = 189
DEFAULT_RESERVE = 200
MATCH_PAGE_LIMIT = 100


@dataclass
class PlannedRequest:
    category: str
    label: str
    path: Path
    endpoint: str
    params: dict[str, Any]


def locate_cached_file(raw_root: Path, filename: str) -> Path | None:
    matches = sorted(raw_root.rglob(filename))
    return matches[0] if matches else None


def current_team_records(raw_root: Path) -> list[dict[str, Any]]:
    source = locate_cached_file(raw_root, "teams_2627.json")

    if source is None:
        raise FileNotFoundError(
            "teams_2627.json was not found below "
            f"{raw_root}. Run the coverage test first."
        )

    payload = load_json(source)
    records = ((payload.get("data") or {}).get("teams") or [])

    if not records:
        raise ValueError(f"No teams were found in {source}")

    return records


def extract_team_id(record: dict[str, Any]) -> int:
    team = record.get("team") or {}
    value = team.get("team_id")

    if value is None:
        raise ValueError(f"Team record has no nested team_id: {record}")

    return int(value)


def extract_team_name(record: dict[str, Any]) -> str:
    team = record.get("team") or {}
    return str(
        team.get("team_name_clean")
        or team.get("team_name")
        or team.get("full_name")
        or extract_team_id(record)
    )


def infer_total_pages_from_cache(
    raw_root: Path,
    season_label: str,
) -> int:
    first = locate_cached_file(
        raw_root,
        f"matches_{season_label}_page_1.json",
    )

    if first is None:
        return 4

    return pagination_total_pages(load_json(first))


def build_plan(
    raw_root: Path,
    output_root: Path,
    include_players: bool,
    include_team_stats: bool,
    include_matches: bool,
    force: bool,
) -> list[PlannedRequest]:
    plan: list[PlannedRequest] = []
    teams = current_team_records(raw_root)

    for record in teams:
        team_id = extract_team_id(record)
        team_name = extract_team_name(record)

        if include_players:
            filename = f"team_{team_id}_players.json"
            cached = locate_cached_file(raw_root, filename)
            target = output_root / "players" / filename

            if force or (cached is None and not target.exists()):
                plan.append(
                    PlannedRequest(
                        category="players",
                        label=f"{team_name} players",
                        path=target,
                        endpoint=f"/teams/{team_id}/players",
                        params={
                            "season_id": CURRENT_SEASON_ID,
                            "league_id": CURRENT_EPL_LEAGUE_ID,
                            "page": 1,
                            "limit": 100,
                        },
                    )
                )

        if include_team_stats:
            filename = f"team_{team_id}_stats_2526.json"
            cached = locate_cached_file(raw_root, filename)
            target = output_root / "team_stats" / filename

            if force or (cached is None and not target.exists()):
                plan.append(
                    PlannedRequest(
                        category="team_stats",
                        label=f"{team_name} 2025/26 team stats",
                        path=target,
                        endpoint=f"/teams/{team_id}/stats",
                        params={"season_id": HISTORICAL_EPL_SEASON_ID},
                    )
                )

    if include_matches:
        season_specs = [
            ("2526", HISTORICAL_EPL_SEASON_ID),
            ("2627", CURRENT_SEASON_ID),
        ]

        for season_label, season_id in season_specs:
            total_pages = infer_total_pages_from_cache(
                raw_root,
                season_label,
            )

            for page in range(1, total_pages + 1):
                filename = f"matches_{season_label}_page_{page}.json"
                cached = locate_cached_file(raw_root, filename)
                target = output_root / "matches" / filename

                if force or (cached is None and not target.exists()):
                    plan.append(
                        PlannedRequest(
                            category="matches",
                            label=f"{season_label} matches page {page}",
                            path=target,
                            endpoint=f"/seasons/{season_id}/matches",
                            params={
                                "page": page,
                                "limit": MATCH_PAGE_LIMIT,
                            },
                        )
                    )

    return plan


def print_plan(plan: list[PlannedRequest], reserve: int) -> None:
    print("\nFootballData.io refresh preview")
    print("=" * 60)

    grouped: dict[str, int] = {}
    for request in plan:
        grouped[request.category] = grouped.get(request.category, 0) + 1

    for category, count in sorted(grouped.items()):
        print(f"{category:15} {count:3} request(s)")

    print("-" * 60)
    print(f"Planned requests: {len(plan)}")
    print(f"Protected reserve: {reserve}")
    print(
        "Cached files are skipped. Preview mode makes zero API requests."
    )

    if not plan:
        print("Everything requested is already cached.")


def player_count(payload: dict[str, Any]) -> int:
    data = payload.get("data") or {}
    players = data.get("players") or []
    return len(players) if isinstance(players, list) else 0


def validate_player_payload(
    payload: dict[str, Any],
    expected_season_id: int,
) -> None:
    meta = payload.get("meta") or {}
    filters = meta.get("filters") or {}
    returned_season = filters.get("season_id")

    if returned_season is not None and int(returned_season) != expected_season_id:
        raise FootballDataError(
            "Footballdata.io returned a roster for the wrong season: "
            f"expected {expected_season_id}, received {returned_season}."
        )


def run_request(
    client: FootballDataClient,
    item: PlannedRequest,
):
    if item.category == "players":
        team_id = int(item.endpoint.split("/")[2])
        return client.team_players(
            team_id=team_id,
            season_id=int(item.params["season_id"]),
            page=int(item.params.get("page", 1)),
            limit=int(item.params.get("limit", 100)),
        )

    if item.category == "team_stats":
        team_id = int(item.endpoint.split("/")[2])
        return client.team_stats(
            team_id=team_id,
            season_id=HISTORICAL_EPL_SEASON_ID,
        )

    if item.category == "matches":
        season_id = int(item.endpoint.split("/")[2])
        return client.season_matches(
            season_id=season_id,
            page=int(item.params["page"]),
            limit=int(item.params["limit"]),
        )

    raise ValueError(f"Unsupported request category: {item.category}")


def run_foundation_builder() -> None:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "build_draft_foundation.py"),
    ]

    print("\nRebuilding normalized analytics...")
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "The API refresh completed, but build_draft_foundation.py failed."
        )


def write_manifest(
    output_root: Path,
    rows: list[dict[str, Any]],
) -> Path:
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requests_attempted": len(rows),
        "results": rows,
    }

    path = output_root / "refresh_manifest.json"
    save_json(manifest, path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Cache-first Footballdata.io full-league refresh. "
            "Preview mode is the default and makes no API requests."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually make the planned API requests.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload files even when a cached copy exists.",
    )
    parser.add_argument(
        "--reserve",
        type=int,
        default=DEFAULT_RESERVE,
        help="Minimum monthly requests to leave unused.",
    )
    parser.add_argument(
        "--skip-players",
        action="store_true",
    )
    parser.add_argument(
        "--skip-team-stats",
        action="store_true",
    )
    parser.add_argument(
        "--skip-matches",
        action="store_true",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Do not rebuild normalized analytics after downloading.",
    )
    args = parser.parse_args()

    raw_root = PROJECT_ROOT / "data" / "raw" / "footballdata_io"
    output_root = raw_root / "full_refresh"

    plan = build_plan(
        raw_root=raw_root,
        output_root=output_root,
        include_players=not args.skip_players,
        include_team_stats=not args.skip_team_stats,
        include_matches=not args.skip_matches,
        force=args.force,
    )

    print_plan(plan, args.reserve)

    if not args.execute:
        print(
            "\nPreview complete. To approve exactly this cached-first plan, run:"
        )
        print(
            "python scripts\\refresh_footballdata_full.py --execute"
        )
        return

    if not plan:
        if not args.skip_build:
            run_foundation_builder()
        return

    client = FootballDataClient()

    # One account-usage request protects the remaining monthly allowance.
    usage = client.account_usage()
    remaining = usage.requests_remaining

    if remaining is None:
        raise FootballDataError(
            "Could not read requests_remaining from /account/usage. "
            "Refresh stopped before downloading."
        )

    required_with_reserve = len(plan) + args.reserve

    print(f"\nRequests currently remaining: {remaining}")
    print(f"Requests required by plan: {len(plan)}")
    print(f"Reserve after refresh: {args.reserve}")

    if remaining < required_with_reserve:
        raise FootballDataError(
            "Refresh cancelled. The planned requests would reduce the "
            f"allowance below the protected reserve of {args.reserve}."
        )

    manifest_rows: list[dict[str, Any]] = []

    for index, item in enumerate(plan, start=1):
        print(f"[{index}/{len(plan)}] {item.label}")

        row = {
            "category": item.category,
            "label": item.label,
            "target": str(item.path),
            "success": False,
            "error": "",
        }

        try:
            result = run_request(client, item)

            if item.category == "players":
                validate_player_payload(
                    result.payload,
                    expected_season_id=CURRENT_SEASON_ID,
                )
                count = player_count(result.payload)
                row["player_count"] = count

                if count == 0:
                    raise FootballDataError(
                        "The API returned zero players for this current-season "
                        "team roster. The existing cache was not overwritten. "
                        "This indicates that player-roster coverage is not "
                        "available for season_id=103535 on the current API plan/feed."
                    )

            save_json(result.payload, item.path)
            row["success"] = True
            row["requests_remaining"] = result.requests_remaining
            print(f"  Saved: {item.path.relative_to(PROJECT_ROOT)}")

        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"  WARNING: {row['error']}")

        manifest_rows.append(row)

    manifest_path = write_manifest(output_root, manifest_rows)
    successful = sum(bool(row["success"]) for row in manifest_rows)
    failed = len(manifest_rows) - successful

    print("\nRefresh finished.")
    print(f"Successful downloads: {successful}")
    print(f"Failed downloads: {failed}")
    print(f"Manifest: {manifest_path.relative_to(PROJECT_ROOT)}")

    if not args.skip_build:
        run_foundation_builder()


if __name__ == "__main__":
    main()
