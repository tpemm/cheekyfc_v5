from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


def load_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")

    if payload.get("success") is False:
        raise ValueError(f"API response reported failure in {path}")

    return payload


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    return html.unescape(str(value)).strip()


def as_number(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def nested(record: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = record
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def discover_json_files(
    folder: str | Path,
    patterns: Iterable[str],
) -> list[Path]:
    folder = Path(folder)
    files: list[Path] = []

    for pattern in patterns:
        files.extend(folder.glob(pattern))

    return sorted(set(files))


def normalize_teams(payload: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for item in nested(payload, "data", "teams", default=[]) or []:
        team = item.get("team") or {}
        season_context = item.get("season_context") or {}
        venue = item.get("venue") or {}

        rows.append(
            {
                "team_id": team.get("team_id"),
                "season_team_id": item.get("season_team_id"),
                "team_name": clean_text(team.get("team_name_clean") or team.get("team_name")),
                "team_full_name": clean_text(team.get("full_name")),
                "team_logo": team.get("team_logo"),
                "country": clean_text(team.get("country")),
                "season_label": season_context.get("season_label"),
                "table_position_raw": season_context.get("table_position"),
                "performance_rank_raw": season_context.get("performance_rank"),
                "risk_raw": season_context.get("risk"),
                "stadium_name": clean_text(venue.get("stadium_name")),
                "founded": item.get("founded"),
            }
        )

    return pd.DataFrame(rows)


def normalize_players(payload: dict[str, Any]) -> pd.DataFrame:
    team = nested(payload, "data", "team", default={}) or {}
    rows: list[dict[str, Any]] = []

    for player in nested(payload, "data", "players", default=[]) or []:
        stats = player.get("stats") or {}
        appearances = as_number(stats.get("appearances"))
        minutes = as_number(stats.get("minutes"))

        impossible_minutes = bool(
            appearances is not None
            and appearances >= 0
            and minutes is not None
            and minutes > appearances * 120
        )

        rows.append(
            {
                "football_data_player_id": player.get("player_id"),
                "football_data_team_id": team.get("team_id"),
                "team_name": clean_text(team.get("team_name")),
                "player_name": clean_text(player.get("known_name") or player.get("player_name")),
                "player_full_name": clean_text(player.get("player_name")),
                "position": clean_text(player.get("position")),
                "nationality": clean_text(player.get("nationality")),
                "date_of_birth": player.get("date_of_birth"),
                "age": as_number(player.get("age")),
                "height_cm": as_number(player.get("height_cm")),
                "weight_kg": as_number(player.get("weight_kg")),
                "player_image": player.get("player_image"),
                "season_id": nested(player, "season", "season_id"),
                "season_year": nested(player, "season", "year"),
                "appearances_api": appearances,
                "minutes_api": minutes,
                "goals_api": as_number(stats.get("goals"), 0),
                "assists_api": as_number(stats.get("assists"), 0),
                "clean_sheets_api": as_number(stats.get("clean_sheets"), 0),
                "goals_conceded_api": as_number(stats.get("goals_conceded"), 0),
                "yellow_cards_api": as_number(stats.get("yellow_cards"), 0),
                "red_cards_api": as_number(stats.get("red_cards"), 0),
                "goals_per_90_api": as_number(stats.get("goals_per_90"), 0),
                "assists_per_90_api": as_number(stats.get("assists_per_90"), 0),
                "minutes_valid": not impossible_minutes,
                "validation_warning": (
                    "minutes exceed appearances × 120"
                    if impossible_minutes
                    else ""
                ),
            }
        )

    return pd.DataFrame(rows)


def normalize_team_stats(payload: dict[str, Any]) -> pd.DataFrame:
    data = payload.get("data") or {}
    team = data.get("team") or {}
    summary = data.get("summary") or {}
    goals = data.get("goals") or {}
    clean_sheets = data.get("clean_sheets") or {}
    failed_to_score = data.get("failed_to_score") or {}
    corners = data.get("corners") or {}
    shots = data.get("shots") or {}
    xg = data.get("xg") or {}
    possession = data.get("possession") or {}
    fouls = data.get("fouls") or {}
    cards = data.get("cards") or {}

    row = {
        "team_id": team.get("team_id"),
        "team_name": clean_text(team.get("team_name_clean") or team.get("team_name")),
        "team_logo": team.get("team_logo"),
        "season_id": nested(data, "season", "season_id"),
        "season_year": nested(data, "season", "year"),
        "matches_played": as_number(summary.get("matches_played")),
        "wins": as_number(summary.get("wins")),
        "draws": as_number(summary.get("draws")),
        "losses": as_number(summary.get("losses")),
        "points_per_game": as_number(summary.get("points_per_game")),
        "win_percentage": as_number(summary.get("win_percentage")),
        "loss_percentage": as_number(summary.get("loss_percentage")),
        "goals_for": as_number(summary.get("goals_for")),
        "goals_against": as_number(summary.get("goals_against")),
        "goals_for_per_match": as_number(goals.get("for_per_match")),
        "goals_against_per_match": as_number(goals.get("against_per_match")),
        "clean_sheet_percentage": as_number(clean_sheets.get("percentage")),
        "failed_to_score_percentage": as_number(failed_to_score.get("percentage")),
        "corners_for_per_match": as_number(corners.get("for_per_match")),
        "corners_against_per_match": as_number(corners.get("against_per_match")),
        "shots_per_match": as_number(shots.get("shots_per_match")),
        "shots_on_target_per_match": as_number(shots.get("shots_on_target_per_match")),
        "shot_conversion_rate": as_number(shots.get("shot_conversion_rate")),
        "xg_for": as_number(xg.get("xg_for")),
        "xg_against": as_number(xg.get("xg_against")),
        "xg_for_per_match": as_number(xg.get("xg_for_per_match")),
        "xg_against_per_match": as_number(xg.get("xg_against_per_match")),
        "possession_average": as_number(possession.get("average")),
        "fouls_committed_per_match": as_number(fouls.get("committed_per_match")),
        "fouls_drawn_per_match": as_number(fouls.get("against_per_match")),
        "cards_for_per_match": as_number(cards.get("for_per_match")),
        "form_string": nested(data, "form", "overall"),
        "last_updated": data.get("last_updated"),
    }

    return pd.DataFrame([row])


def normalize_matches(payload: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for match in nested(payload, "data", "matches", default=[]) or []:
        home = match.get("home_team") or {}
        away = match.get("away_team") or {}
        score = match.get("score") or {}
        xg = match.get("xg") or {}
        odds = match.get("odds") or {}
        probabilities = match.get("probabilities") or {}
        venue = match.get("venue") or {}

        home_score = as_number(score.get("home"), 0) or 0
        away_score = as_number(score.get("away"), 0) or 0
        total_goals_api = as_number(score.get("total_goals"), 0) or 0
        calculated_total = home_score + away_score

        score_total_valid = (
            str(match.get("status", "")).lower() != "complete"
            or total_goals_api == calculated_total
        )

        rows.append(
            {
                "match_id": match.get("match_id"),
                "match_date": match.get("match_date"),
                "date_unix": match.get("date_unix"),
                "status": match.get("status"),
                "status_localized": match.get("status_localized"),
                "round_id": match.get("round_id"),
                "game_week_api": match.get("game_week"),
                "season_id": nested(match, "season", "season_id"),
                "season_year": nested(match, "season", "year"),
                "home_team_id": home.get("team_id"),
                "home_team": clean_text(home.get("team_name")),
                "away_team_id": away.get("team_id"),
                "away_team": clean_text(away.get("team_name")),
                "home_score": home_score,
                "away_score": away_score,
                "total_goals_api": total_goals_api,
                "total_goals_calculated": calculated_total,
                "score_total_valid": score_total_valid,
                "home_xg": as_number(xg.get("home"), 0),
                "away_xg": as_number(xg.get("away"), 0),
                "total_xg": as_number(xg.get("total"), 0),
                "home_odds": as_number(odds.get("home_win"), 0),
                "draw_odds": as_number(odds.get("draw"), 0),
                "away_odds": as_number(odds.get("away_win"), 0),
                "home_win_probability": as_number(probabilities.get("home_win"), 0),
                "draw_probability": as_number(probabilities.get("draw"), 0),
                "away_win_probability": as_number(probabilities.get("away_win"), 0),
                "stadium_name": clean_text(venue.get("stadium_name")),
                "last_updated": match.get("last_updated"),
                "validation_warning": (
                    ""
                    if score_total_valid
                    else "score.total_goals does not equal home + away"
                ),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["match_date"] = pd.to_datetime(frame["match_date"], errors="coerce")
    frame = frame.sort_values(["match_date", "match_id"]).reset_index(drop=True)

    # Footballdata.io currently returns null game_week values for 2026/27.
    # This estimate is explicitly labeled and must not overwrite API gameweeks.
    frame["fixture_order"] = range(1, len(frame) + 1)
    frame["game_week_estimate"] = ((frame["fixture_order"] - 1) // 10) + 1
    frame["game_week"] = frame["game_week_api"].fillna(frame["game_week_estimate"])
    frame["game_week_is_estimated"] = frame["game_week_api"].isna()

    return frame


def combine_json_normalizations(
    files: Iterable[str | Path],
    normalizer,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for path in files:
        frame = normalizer(load_json(path))
        if not frame.empty:
            frame["source_file"] = str(path)
            frames.append(frame)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)
