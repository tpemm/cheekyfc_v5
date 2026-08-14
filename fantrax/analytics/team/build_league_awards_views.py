#!/usr/bin/env python3
r"""
build_league_awards_views.py

Purpose
-------
Build dashboard-ready analytics views for the Fantrax app.

This version separates two ideas:

1. Weekly awards:
   Who won the award in each individual gameweek.

2. Season leaderboards:
   Who leads the full-season total/average for that metric.

Examples:
- Golden Boot leaderboard = total starter goals all season.
- Golden Assist leaderboard = total starter assists all season.
- Golden Gloves leaderboard = total starter clean sheets all season.
- Bench Merchant leaderboard = total bench points + avg bench points.
- xG Merchant leaderboard = total starter xG.
- Jester leaderboard = weekly Jester count + avg starter points.

Inputs:
    C:\Users\Tommy\fantrax_data\data\processed\manager_week_summary_2526.csv
    C:\Users\Tommy\fantrax_data\data\processed\manager_season_summary_2526.csv
    C:\Users\Tommy\fantrax_data\data\processed\matchup_week_summary_2526.csv
    C:\Users\Tommy\fantrax_data\data\processed\manager_player_weekly_2526.csv

Outputs:
    C:\Users\Tommy\fantrax_data\data\analytics_views\*.csv
"""

from __future__ import annotations

import sys

from pathlib import Path
import pandas as pd


# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
SEASON_ID = "2526"

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
API_DIR = PROJECT_ROOT / "processed_data" / "fantrax_api"
OUT_DIR = PROJECT_ROOT / "data" / "analytics_views"

MANAGER_WEEK_FILE = PROCESSED_DIR / f"manager_week_summary_{SEASON_ID}.csv"
MANAGER_SEASON_FILE = PROCESSED_DIR / f"manager_season_summary_{SEASON_ID}.csv"
MATCHUP_WEEK_FILE = PROCESSED_DIR / f"matchup_week_summary_{SEASON_ID}.csv"
MANAGER_PLAYER_FILE = PROCESSED_DIR / f"manager_player_weekly_{SEASON_ID}.csv"
STANDINGS_FILE = API_DIR / "standings.csv"

OUT_LEAGUE_TABLE = OUT_DIR / "league_table.csv"
OUT_WEEKLY_AWARDS = OUT_DIR / "weekly_awards.csv"
OUT_AWARD_LEADERBOARDS = OUT_DIR / "award_leaderboards.csv"
OUT_MANAGER_STREAKS = OUT_DIR / "manager_streaks.csv"
OUT_LINEUP_CHANGES = OUT_DIR / "lineup_changes.csv"
OUT_CLOSEST_GAMES = OUT_DIR / "closest_games.csv"
OUT_BIGGEST_BLOWOUTS = OUT_DIR / "biggest_blowouts.csv"
OUT_HUB_CARDS = OUT_DIR / "league_hub_cards.csv"
OUT_REPORT = OUT_DIR / "league_awards_report.txt"


AWARD_CONFIG = {
    "Jester": {
        "metric_col": "starter_fantasy_points",
        "weekly_high_wins": False,
        "leaderboard_sort_col": "jester_award_wins",
        "leaderboard_value_col": "jester_award_wins",
        "leaderboard_value_label": "Weekly Jesters",
        "detail_cols": ["season_avg_starter_points", "season_total_starter_points"],
        "description": "Lowest starter fantasy points in a gameweek.",
    },
    "Golden Boot": {
        "metric_col": "starter_goals",
        "weekly_high_wins": True,
        "leaderboard_sort_col": "season_total",
        "leaderboard_value_col": "season_total",
        "leaderboard_value_label": "Season Starter Goals",
        "description": "Total goals scored by active starters all season.",
    },
    "Golden Assist": {
        "metric_col": "starter_assists_total",
        "weekly_high_wins": True,
        "leaderboard_sort_col": "season_total",
        "leaderboard_value_col": "season_total",
        "leaderboard_value_label": "Season Starter Assists",
        "description": "Total assists by active starters all season.",
    },
    "Golden Gloves": {
        "metric_col": "starter_clean_sheets",
        "weekly_high_wins": True,
        "leaderboard_sort_col": "season_total",
        "leaderboard_value_col": "season_total",
        "leaderboard_value_label": "Season Starter Clean Sheets",
        "description": "Total clean sheets from active starters all season.",
    },
    "Bench Merchant": {
        "metric_col": "bench_fantasy_points",
        "weekly_high_wins": True,
        "leaderboard_sort_col": "season_total",
        "leaderboard_value_col": "season_total",
        "leaderboard_value_label": "Season Bench Points",
        "detail_cols": ["season_avg"],
        "description": "Total fantasy points left on the bench all season.",
    },
    "xG Merchant": {
        "metric_col": "starter_xg",
        "weekly_high_wins": True,
        "leaderboard_sort_col": "season_total",
        "leaderboard_value_col": "season_total",
        "leaderboard_value_label": "Season Starter xG",
        "description": "Total starter xG all season.",
    },
    "Minutes Merchant": {
        "metric_col": "starter_minutes",
        "weekly_high_wins": True,
        "leaderboard_sort_col": "season_total",
        "leaderboard_value_col": "season_total",
        "leaderboard_value_label": "Season Starter Minutes",
        "description": "Total minutes played by active starters all season.",
    },
}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path, encoding="utf-8-sig")


def clean_display_name(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    text = text.replace("â€™", "’")
    for bad in ["🤡", "ðŸ¤¡"]:
        text = text.replace(bad, "")
    return " ".join(text.split()).strip()


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved: {path} rows={len(df):,}")
    if len(df):
        print(df.head(5).to_string(index=False))
    print()


def clean_team_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["api_team_name", "opponent_team_name", "team_name", "opponent_name_from_summary"]:
        if col in out.columns:
            out[col] = out[col].map(clean_display_name)
    return out


def winner_rows_by_week(
    df: pd.DataFrame,
    award_name: str,
    metric_col: str,
    high_wins: bool,
    value_label: str,
) -> pd.DataFrame:
    rows = []

    if metric_col not in df.columns:
        return pd.DataFrame()

    for gw, g in df.groupby("fantrax_gw", dropna=False):
        metric = pd.to_numeric(g[metric_col], errors="coerce")
        if metric.isna().all():
            continue

        target = metric.max() if high_wins else metric.min()
        winners = g[metric == target].copy()

        for _, row in winners.iterrows():
            rows.append({
                "fantrax_gw": gw,
                "award_name": award_name,
                "award_type": "weekly",
                "api_team_id": row.get("api_team_id"),
                "api_team_name": row.get("api_team_name"),
                "metric_col": metric_col,
                "metric_label": value_label,
                "metric_value": target,
                "winner_count_for_week": len(winners),
            })

    return pd.DataFrame(rows)


def build_weekly_awards(manager_week: pd.DataFrame, matchup_week: pd.DataFrame) -> pd.DataFrame:
    frames = []

    for award_name, cfg in AWARD_CONFIG.items():
        frames.append(
            winner_rows_by_week(
                manager_week,
                award_name,
                cfg["metric_col"],
                cfg["weekly_high_wins"],
                cfg["leaderboard_value_label"],
            )
        )

    # Closest game is a matchup award, not manager-season stat.
    if len(matchup_week) and "point_margin_vs_opponent" in matchup_week.columns:
        mg = matchup_week.copy()
        mg["abs_margin"] = pd.to_numeric(mg["point_margin_vs_opponent"], errors="coerce").abs()

        rows = []
        for gw, g in mg.dropna(subset=["abs_margin"]).groupby("fantrax_gw", dropna=False):
            min_margin = g["abs_margin"].min()
            close_rows = g[g["abs_margin"] == min_margin]
            for _, row in close_rows.iterrows():
                rows.append({
                    "fantrax_gw": gw,
                    "award_name": "Closest Game",
                    "award_type": "weekly_matchup",
                    "api_team_id": row.get("api_team_id"),
                    "api_team_name": row.get("api_team_name"),
                    "opponent_team_id": row.get("opponent_team_id"),
                    "opponent_team_name": row.get("opponent_team_name"),
                    "metric_col": "abs_margin",
                    "metric_label": "Point margin",
                    "metric_value": min_margin,
                    "winner_count_for_week": len(close_rows),
                })
        frames.append(pd.DataFrame(rows))

    out = pd.concat([f for f in frames if len(f)], ignore_index=True) if frames else pd.DataFrame()
    if len(out):
        out = clean_team_cols(out)
        out = out.sort_values(["fantrax_gw", "award_name", "api_team_name"])
    return out


def build_award_leaderboards(weekly_awards: pd.DataFrame, manager_week: pd.DataFrame) -> pd.DataFrame:
    rows = []

    if manager_week.empty:
        return pd.DataFrame()

    # Weekly award counts.
    if weekly_awards.empty:
        weekly_counts = pd.DataFrame()
    else:
        weekly_counts = (
            weekly_awards
            .groupby(["award_name", "api_team_id", "api_team_name"], dropna=False)
            .agg(
                weekly_award_wins=("fantrax_gw", "count"),
                best_week_value=("metric_value", "max"),
                avg_winning_value=("metric_value", "mean"),
                weeks_won=("fantrax_gw", lambda s: ",".join(map(str, sorted(set(pd.to_numeric(s, errors="coerce").dropna().astype(int)))))),
            )
            .reset_index()
        )

        # Jester best week should be lowest, not max.
        jester = weekly_awards[weekly_awards["award_name"] == "Jester"]
        if len(jester):
            jester_best = (
                jester.groupby(["award_name", "api_team_id", "api_team_name"], dropna=False)["metric_value"]
                .min()
                .reset_index(name="jester_lowest_week_value")
            )
            weekly_counts = weekly_counts.merge(jester_best, on=["award_name", "api_team_id", "api_team_name"], how="left")
            mask = weekly_counts["award_name"].eq("Jester")
            weekly_counts.loc[mask, "best_week_value"] = weekly_counts.loc[mask, "jester_lowest_week_value"]
            weekly_counts = weekly_counts.drop(columns=["jester_lowest_week_value"])

    team_base = manager_week[["api_team_id", "api_team_name"]].drop_duplicates().copy()

    for award_name, cfg in AWARD_CONFIG.items():
        metric_col = cfg["metric_col"]
        if metric_col not in manager_week.columns:
            continue

        season = (
            manager_week
            .groupby(["api_team_id", "api_team_name"], dropna=False)
            .agg(
                weeks=("fantrax_gw", "nunique"),
                season_total=(metric_col, "sum"),
                season_avg=(metric_col, "mean"),
                season_best_week=(metric_col, "max"),
                season_worst_week=(metric_col, "min"),
            )
            .reset_index()
        )

        season["award_name"] = award_name
        season["metric_col"] = metric_col
        season["metric_label"] = cfg["leaderboard_value_label"]
        season["description"] = cfg["description"]

        counts = weekly_counts[weekly_counts["award_name"] == award_name].copy() if len(weekly_counts) else pd.DataFrame()
        if len(counts):
            season = season.merge(
                counts[
                    [
                        "api_team_id",
                        "award_name",
                        "weekly_award_wins",
                        "best_week_value",
                        "avg_winning_value",
                        "weeks_won",
                    ]
                ],
                on=["api_team_id", "award_name"],
                how="left",
            )
        else:
            season["weekly_award_wins"] = 0
            season["best_week_value"] = pd.NA
            season["avg_winning_value"] = pd.NA
            season["weeks_won"] = ""

        season["weekly_award_wins"] = pd.to_numeric(season["weekly_award_wins"], errors="coerce").fillna(0).astype(int)
        season["weeks_won"] = season["weeks_won"].fillna("")

        # Extra jester context.
        if award_name == "Jester":
            season = season.rename(columns={
                "weekly_award_wins": "jester_award_wins",
                "season_total": "season_total_starter_points",
                "season_avg": "season_avg_starter_points",
            })
            season["leaderboard_value"] = season["jester_award_wins"]
            season["leaderboard_value_label"] = "Weekly Jesters"
            season = season.sort_values(
                ["jester_award_wins", "season_avg_starter_points"],
                ascending=[False, True],
            )
            # Keep common columns available.
            season["season_total"] = season["season_total_starter_points"]
            season["season_avg"] = season["season_avg_starter_points"]
            season["weekly_award_wins"] = season["jester_award_wins"]
        else:
            season["leaderboard_value"] = season["season_total"]
            season["leaderboard_value_label"] = cfg["leaderboard_value_label"]
            season = season.sort_values(
                ["season_total", "weekly_award_wins", "season_best_week"],
                ascending=[False, False, False],
            )

        season["rank"] = range(1, len(season) + 1)
        rows.append(season)

    # Add Closest Game leaderboard separately: count close-game appearances and avg closest margin.
    if "Closest Game" in set(weekly_awards.get("award_name", pd.Series(dtype=str))):
        cg = weekly_awards[weekly_awards["award_name"] == "Closest Game"].copy()
        closest_lb = (
            cg.groupby(["api_team_id", "api_team_name"], dropna=False)
            .agg(
                weekly_award_wins=("fantrax_gw", "count"),
                season_total=("metric_value", "sum"),
                season_avg=("metric_value", "mean"),
                season_best_week=("metric_value", "min"),
                season_worst_week=("metric_value", "max"),
                weeks_won=("fantrax_gw", lambda s: ",".join(map(str, sorted(set(pd.to_numeric(s, errors="coerce").dropna().astype(int)))))),
            )
            .reset_index()
        )
        closest_lb["award_name"] = "Closest Game"
        closest_lb["metric_col"] = "abs_margin"
        closest_lb["metric_label"] = "Point margin"
        closest_lb["description"] = "Closest matchup appearances by point margin."
        closest_lb["leaderboard_value"] = closest_lb["weekly_award_wins"]
        closest_lb["leaderboard_value_label"] = "Closest Game Appearances"
        closest_lb["best_week_value"] = closest_lb["season_best_week"]
        closest_lb["avg_winning_value"] = closest_lb["season_avg"]
        closest_lb = closest_lb.sort_values(["weekly_award_wins", "season_best_week"], ascending=[False, True])
        closest_lb["rank"] = range(1, len(closest_lb) + 1)
        rows.append(closest_lb)

    out = pd.concat(rows, ignore_index=True, sort=False) if rows else pd.DataFrame()
    if len(out):
        out = clean_team_cols(out)
        out = out.sort_values(["award_name", "rank"])
    return out


def build_manager_streaks(matchup_week: pd.DataFrame) -> pd.DataFrame:
    if matchup_week.empty or "computed_result" not in matchup_week.columns:
        return pd.DataFrame()

    rows = []
    mw = matchup_week.copy()
    mw["fantrax_gw"] = pd.to_numeric(mw["fantrax_gw"], errors="coerce").astype("Int64")
    mw = mw.sort_values(["api_team_id", "fantrax_gw"])

    for team_id, g in mw.groupby("api_team_id", dropna=False):
        g = g.sort_values("fantrax_gw")
        team_name = g["api_team_name"].dropna().iloc[0] if g["api_team_name"].notna().any() else team_id

        longest_win = 0
        longest_loss = 0
        running_win = 0
        running_loss = 0
        running_win_weeks: list[int] = []
        running_loss_weeks: list[int] = []
        longest_win_weeks: list[int] = []
        longest_loss_weeks: list[int] = []
        results = []

        for _, row in g.iterrows():
            result = row.get("computed_result")
            gw = int(row.get("fantrax_gw"))
            results.append(str(result))

            if result == "W":
                running_win += 1
                running_win_weeks.append(gw)
                running_loss = 0
                running_loss_weeks = []
            elif result == "L":
                running_loss += 1
                running_loss_weeks.append(gw)
                running_win = 0
                running_win_weeks = []
            else:
                running_win = 0
                running_loss = 0
                running_win_weeks = []
                running_loss_weeks = []

            if running_win > longest_win:
                longest_win = running_win
                longest_win_weeks = running_win_weeks.copy()
            if running_loss > longest_loss:
                longest_loss = running_loss
                longest_loss_weeks = running_loss_weeks.copy()

        current_type = ""
        current_len = 0
        current_weeks: list[int] = []
        if results:
            last = results[-1]
            if last in {"W", "L"}:
                current_type = last
                rev_g = list(g.sort_values("fantrax_gw", ascending=False).itertuples())
                for row in rev_g:
                    if getattr(row, "computed_result") == last:
                        current_len += 1
                        current_weeks.append(int(getattr(row, "fantrax_gw")))
                    else:
                        break
                current_weeks = sorted(current_weeks)

        rows.append({
            "api_team_id": team_id,
            "api_team_name": clean_display_name(team_name),
            "wins": sum(1 for r in results if r == "W"),
            "losses": sum(1 for r in results if r == "L"),
            "ties": sum(1 for r in results if r == "T"),
            "longest_win_streak": longest_win,
            "longest_win_streak_weeks": ",".join(map(str, longest_win_weeks)),
            "longest_losing_streak": longest_loss,
            "longest_losing_streak_weeks": ",".join(map(str, longest_loss_weeks)),
            "current_streak_type": current_type,
            "current_streak_len": current_len,
            "current_streak_weeks": ",".join(map(str, current_weeks)),
            "result_sequence": "".join(results),
        })

    out = pd.DataFrame(rows)
    if len(out):
        out = clean_team_cols(out)
        out = out.sort_values(["longest_win_streak", "wins"], ascending=[False, False])
    return out


def build_lineup_changes(manager_player: pd.DataFrame) -> pd.DataFrame:
    required = {"fantrax_gw", "api_team_id", "api_team_name", "fantrax_player_id", "is_started_api", "is_rostered_api"}
    if manager_player.empty or not required.issubset(set(manager_player.columns)):
        return pd.DataFrame()

    mp = manager_player.copy()
    mp = mp[mp["is_rostered_api"].astype(str).str.lower().isin(["true", "1", "yes"])]
    mp["fantrax_gw"] = pd.to_numeric(mp["fantrax_gw"], errors="coerce").astype("Int64")
    mp["is_started_api_bool"] = mp["is_started_api"].astype(str).str.lower().isin(["true", "1", "yes"])

    rows = []

    for team_id, g in mp.groupby("api_team_id", dropna=False):
        team_name = clean_display_name(g["api_team_name"].dropna().iloc[0] if g["api_team_name"].notna().any() else team_id)
        prev_starters = None
        prev_roster = None

        for gw, week in g.groupby("fantrax_gw", dropna=False):
            starters = set(week.loc[week["is_started_api_bool"], "fantrax_player_id"].dropna().astype(str))
            roster = set(week["fantrax_player_id"].dropna().astype(str))

            if prev_starters is None:
                starter_added = set()
                starter_removed = set()
                roster_added = set()
                roster_removed = set()
            else:
                starter_added = starters - prev_starters
                starter_removed = prev_starters - starters
                roster_added = roster - prev_roster
                roster_removed = prev_roster - roster

            rows.append({
                "fantrax_gw": gw,
                "api_team_id": team_id,
                "api_team_name": team_name,
                "starter_count": len(starters),
                "roster_count": len(roster),
                "starter_changes": len(starter_added) + len(starter_removed),
                "starters_added": len(starter_added),
                "starters_removed": len(starter_removed),
                "roster_turnover": len(roster_added) + len(roster_removed),
                "roster_added": len(roster_added),
                "roster_removed": len(roster_removed),
                "starters_added_ids": ",".join(sorted(starter_added)),
                "starters_removed_ids": ",".join(sorted(starter_removed)),
                "roster_added_ids": ",".join(sorted(roster_added)),
                "roster_removed_ids": ",".join(sorted(roster_removed)),
                "view_type": "weekly",
            })

            prev_starters = starters
            prev_roster = roster

    weekly = pd.DataFrame(rows)
    if weekly.empty:
        return weekly

    season = (
        weekly
        .groupby(["api_team_id", "api_team_name"], dropna=False)
        .agg(
            weeks=("fantrax_gw", "nunique"),
            total_starter_changes=("starter_changes", "sum"),
            avg_starter_changes=("starter_changes", "mean"),
            max_starter_changes_week=("starter_changes", "max"),
            total_roster_turnover=("roster_turnover", "sum"),
            avg_roster_turnover=("roster_turnover", "mean"),
            max_roster_turnover_week=("roster_turnover", "max"),
        )
        .reset_index()
    )
    season["view_type"] = "season_summary"

    return pd.concat([weekly, season], ignore_index=True, sort=False)


def build_matchup_extremes(matchup_week: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if matchup_week.empty or "point_margin_vs_opponent" not in matchup_week.columns:
        return pd.DataFrame(), pd.DataFrame()

    m = matchup_week.copy()
    m["abs_margin"] = pd.to_numeric(m["point_margin_vs_opponent"], errors="coerce").abs()
    m["starter_fantasy_points"] = pd.to_numeric(m["starter_fantasy_points"], errors="coerce")
    m["opponent_starter_fantasy_points"] = pd.to_numeric(m["opponent_starter_fantasy_points"], errors="coerce")

    games = m[m["home_away"] == "home"].copy()
    if games.empty:
        games = m.sort_values(["fantrax_gw", "matchup_index"]).drop_duplicates(["fantrax_gw", "matchup_index"])

    keep = [
        "fantrax_gw", "matchup_index", "api_team_id", "api_team_name",
        "starter_fantasy_points", "opponent_team_id", "opponent_team_name",
        "opponent_starter_fantasy_points", "point_margin_vs_opponent",
        "abs_margin", "computed_result",
    ]

    closest = clean_team_cols(games.sort_values(["abs_margin", "fantrax_gw"], ascending=[True, True]))
    blowouts = clean_team_cols(games.sort_values(["abs_margin", "fantrax_gw"], ascending=[False, True]))
    return closest[[c for c in keep if c in closest.columns]], blowouts[[c for c in keep if c in blowouts.columns]]


def build_league_table(manager_season: pd.DataFrame, streaks: pd.DataFrame) -> pd.DataFrame:
    table = manager_season.copy()
    table = clean_team_cols(table)

    if len(streaks):
        table = table.merge(
            streaks[[
                "api_team_id", "longest_win_streak", "longest_win_streak_weeks",
                "longest_losing_streak", "longest_losing_streak_weeks",
                "current_streak_type", "current_streak_len", "current_streak_weeks",
            ]],
            on="api_team_id",
            how="left",
        )

    if "official_rank" in table.columns:
        table["_rank_num"] = pd.to_numeric(table["official_rank"], errors="coerce")
        table = table.sort_values(["_rank_num", "api_team_name"]).drop(columns=["_rank_num"])
    else:
        table = table.sort_values("total_starter_points", ascending=False)

    return table


def build_hub_cards(
    award_leaderboards: pd.DataFrame,
    streaks: pd.DataFrame,
    lineup_changes: pd.DataFrame,
    closest: pd.DataFrame,
    blowouts: pd.DataFrame,
) -> pd.DataFrame:
    cards = []

    def add_card(card_id: str, title: str, subtitle: str, team_name: str, value: object, detail: str = ""):
        cards.append({
            "card_id": card_id,
            "title": title,
            "subtitle": subtitle,
            "team_name": clean_display_name(team_name),
            "value": value,
            "detail": detail,
        })

    for award in ["Jester", "Golden Boot", "Golden Assist", "Golden Gloves", "Bench Merchant", "xG Merchant"]:
        sub = award_leaderboards[award_leaderboards["award_name"] == award].copy() if len(award_leaderboards) else pd.DataFrame()
        if len(sub):
            top = sub.sort_values("rank").iloc[0]
            value = top.get("leaderboard_value", "")
            detail = top.get("leaderboard_value_label", "")
            if award == "Bench Merchant":
                detail = f"{detail} | avg {top.get('season_avg', 0):.1f}/GW"
            if award == "Jester":
                detail = f"weekly Jesters | avg pts {top.get('season_avg_starter_points', 0):.1f}"
            add_card(
                card_id=award.lower().replace(" ", "_"),
                title=award,
                subtitle="Season leader",
                team_name=top.get("api_team_name", ""),
                value=value,
                detail=detail,
            )

    if len(streaks):
        top_win = streaks.sort_values(["longest_win_streak", "wins"], ascending=[False, False]).iloc[0]
        add_card(
            "longest_win_streak",
            "Longest Win Streak",
            "Best season streak",
            top_win.get("api_team_name", ""),
            top_win.get("longest_win_streak", ""),
            f"weeks {top_win.get('longest_win_streak_weeks', '')}",
        )

        top_loss = streaks.sort_values(["longest_losing_streak", "losses"], ascending=[False, False]).iloc[0]
        add_card(
            "longest_losing_streak",
            "Longest Losing Streak",
            "Pain index",
            top_loss.get("api_team_name", ""),
            top_loss.get("longest_losing_streak", ""),
            f"weeks {top_loss.get('longest_losing_streak_weeks', '')}",
        )

    if len(lineup_changes) and "view_type" in lineup_changes.columns:
        season_lineup = lineup_changes[lineup_changes["view_type"] == "season_summary"].copy()
        if len(season_lineup):
            most = season_lineup.sort_values("total_starter_changes", ascending=False).iloc[0]
            least = season_lineup.sort_values("total_starter_changes", ascending=True).iloc[0]
            add_card("most_lineup_changes", "Most Lineup Changes", "Tinkerman award", most.get("api_team_name", ""), most.get("total_starter_changes", ""), "starter changes")
            add_card("least_lineup_changes", "Least Lineup Changes", "Set-and-forget award", least.get("api_team_name", ""), least.get("total_starter_changes", ""), "starter changes")

    if len(closest):
        row = closest.iloc[0]
        add_card("closest_game", "Closest Game", f"GW {row.get('fantrax_gw')}", f"{row.get('api_team_name')} vs {row.get('opponent_team_name')}", row.get("abs_margin"), "point margin")

    if len(blowouts):
        row = blowouts.iloc[0]
        add_card("biggest_blowout", "Biggest Blowout", f"GW {row.get('fantrax_gw')}", f"{row.get('api_team_name')} vs {row.get('opponent_team_name')}", row.get("abs_margin"), "point margin")

    return pd.DataFrame(cards)


def main() -> None:
    print("Building League Awards Analytics Views")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manager_week = read_csv(MANAGER_WEEK_FILE)
    manager_season = read_csv(MANAGER_SEASON_FILE)
    matchup_week = read_csv(MATCHUP_WEEK_FILE)
    manager_player = read_csv(MANAGER_PLAYER_FILE)

    for df in [manager_week, matchup_week, manager_player]:
        if "fantrax_gw" in df.columns:
            df["fantrax_gw"] = pd.to_numeric(df["fantrax_gw"], errors="coerce").astype("Int64")

    weekly_awards = build_weekly_awards(manager_week, matchup_week)
    award_leaderboards = build_award_leaderboards(weekly_awards, manager_week)
    streaks = build_manager_streaks(matchup_week)
    lineup_changes = build_lineup_changes(manager_player)
    closest, blowouts = build_matchup_extremes(matchup_week)
    league_table = build_league_table(manager_season, streaks)
    hub_cards = build_hub_cards(award_leaderboards, streaks, lineup_changes, closest, blowouts)

    save_csv(league_table, OUT_LEAGUE_TABLE)
    save_csv(weekly_awards, OUT_WEEKLY_AWARDS)
    save_csv(award_leaderboards, OUT_AWARD_LEADERBOARDS)
    save_csv(streaks, OUT_MANAGER_STREAKS)
    save_csv(lineup_changes, OUT_LINEUP_CHANGES)
    save_csv(closest, OUT_CLOSEST_GAMES)
    save_csv(blowouts, OUT_BIGGEST_BLOWOUTS)
    save_csv(hub_cards, OUT_HUB_CARDS)

    report = []
    report.append("League Awards Views Build Report")
    report.append("=" * 80)
    report.append(f"manager_week rows: {len(manager_week):,}")
    report.append(f"manager_season rows: {len(manager_season):,}")
    report.append(f"matchup_week rows: {len(matchup_week):,}")
    report.append(f"manager_player rows: {len(manager_player):,}")
    report.append("")
    report.append(f"league_table rows: {len(league_table):,}")
    report.append(f"weekly_awards rows: {len(weekly_awards):,}")
    report.append(f"award_leaderboards rows: {len(award_leaderboards):,}")
    report.append(f"manager_streaks rows: {len(streaks):,}")
    report.append(f"lineup_changes rows: {len(lineup_changes):,}")
    report.append(f"closest_games rows: {len(closest):,}")
    report.append(f"biggest_blowouts rows: {len(blowouts):,}")
    report.append(f"hub_cards rows: {len(hub_cards):,}")

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print(f"\nSaved report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
