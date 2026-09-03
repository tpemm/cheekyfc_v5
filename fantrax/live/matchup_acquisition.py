"""Authenticated Fantrax live-scoring acquisition and authority normalization."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import pandas as pd

from fantrax.live.weekly_acquisition import _auth_path


MATCHUP_COLUMNS = (
    "season_id", "period", "matchup_id", "home_manager", "away_manager",
    "home_team_id", "away_team_id", "home_score", "away_score", "status",
    "winner", "margin", "source", "acquired_at", "maturity",
)
PLAYER_COLUMNS = (
    "season_id", "period", "fantrax_team_id", "manager", "lineup_status",
    "fantrax_player_id", "player_name", "live_scoring_fpts", "source", "acquired_at",
)


def _live_data(payload: Any) -> dict:
    root = payload if isinstance(payload, dict) else {}
    responses = root.get("responses", [])
    if not responses and isinstance(root.get("data"), dict):
        root = root["data"]
        responses = root.get("responses", [])
    for item in responses:
        data = item.get("data", {}) if isinstance(item, dict) else {}
        if isinstance(data, dict) and "statsPerTeam" in data and "matchups" in data:
            return data
    if isinstance(root, dict) and "statsPerTeam" in root and "matchups" in root:
        return root
    raise ValueError("Fantrax live-scoring response has no matchup scoring payload")


def normalize_live_scoring(payload: Any, *, season_id: str, period: int, acquired_at: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = _live_data(payload)
    teams = data.get("fantasyTeamInfo", {})
    stats = data.get("statsPerTeam", {}).get("allTeamsStats", {})
    all_finished = bool(data.get("allEventsFinished"))
    maturity = "FINAL" if all_finished else "LIVE"
    matchup_rows = []
    for matchup_id in data.get("matchups", []):
        away_id, home_id = str(matchup_id).split("_", 1)
        home_score = pd.to_numeric(stats.get(home_id, {}).get("ACTIVE", {}).get("totalFpts"), errors="coerce")
        away_score = pd.to_numeric(stats.get(away_id, {}).get("ACTIVE", {}).get("totalFpts"), errors="coerce")
        if pd.isna(home_score) or pd.isna(away_score):
            raise ValueError(f"Missing authoritative score for matchup {matchup_id}")
        winner = "TIE" if home_score == away_score else teams[home_id]["name"] if home_score > away_score else teams[away_id]["name"]
        matchup_rows.append({
            "season_id": season_id, "period": int(period), "matchup_id": str(matchup_id),
            "home_manager": teams[home_id]["name"], "away_manager": teams[away_id]["name"],
            "home_team_id": home_id, "away_team_id": away_id,
            "home_score": float(home_score), "away_score": float(away_score),
            "status": "completed" if all_finished else "live", "winner": winner,
            "margin": float(abs(home_score-away_score)), "source": "Fantrax getLiveScoringStats",
            "acquired_at": acquired_at, "maturity": maturity,
        })
    scorer_lookup: dict[tuple[str, str, str], dict] = {}
    for lineup_status, team_map in data.get("scorerMap", {}).items():
        for team_id, groups in team_map.items():
            for players in groups.values():
                for item in players:
                    scorer = item.get("scorer", {})
                    scorer_lookup[(str(team_id), str(lineup_status), str(scorer.get("scorerId")))] = scorer
    player_rows = []
    for (team_id, lineup_status, player_id), scorer in scorer_lookup.items():
        values = stats.get(team_id, {}).get(lineup_status, {}).get("statsMap", {}).get(player_id, {})
        points = pd.to_numeric(values.get("object1", 0.0), errors="coerce")
        player_rows.append({
            "season_id": season_id, "period": int(period), "fantrax_team_id": str(team_id),
            "manager": teams.get(team_id, {}).get("name"), "lineup_status": str(lineup_status),
            "fantrax_player_id": str(player_id), "player_name": scorer.get("name"),
            "live_scoring_fpts": float(points) if pd.notna(points) else 0.0,
            "source": "Fantrax getLiveScoringStats", "acquired_at": acquired_at,
        })
    matchups = pd.DataFrame(matchup_rows, columns=MATCHUP_COLUMNS)
    players = pd.DataFrame(player_rows, columns=PLAYER_COLUMNS)
    team_ids = set(matchups.home_team_id) | set(matchups.away_team_id)
    if len(matchups) != 6 or len(team_ids) != 12 or matchups.matchup_id.duplicated().any():
        raise ValueError(f"Expected six unique matchups and 12 teams; got {len(matchups)} and {len(team_ids)}")
    return matchups, players


def capture_live_scoring(*, league_id: str, period: int, project_root: Path, timeout_ms: int = 60_000) -> dict:
    """Use the commissioner-local authenticated UI; hosted refresh never calls this."""
    from playwright.sync_api import sync_playwright
    auth = _auth_path(project_root)
    if not auth.exists():
        raise RuntimeError(f"Authenticated Fantrax browser state is required: {auth}")
    executable = os.environ.get("FANTRAX_BROWSER_EXECUTABLE", "").strip()
    if not executable and os.name == "nt":
        candidates = (Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"), Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"))
        executable = str(next((path for path in candidates if path.exists()), ""))
    url = f"https://www.fantrax.com/fantasy/league/{league_id}/livescoring;period={int(period)}"
    with sync_playwright() as playwright:
        launch = {"headless": os.environ.get("FANTRAX_HEADLESS", "1").strip().lower() not in {"0", "false", "no"}}
        if executable: launch["executable_path"] = executable
        browser = playwright.chromium.launch(**launch); context = browser.new_context(storage_state=str(auth)); page = context.new_page()
        page.add_init_script("""() => {
            window.__fantraxLiveScoring = null;
            const originalFetch = window.fetch;
            window.fetch = async (...args) => {
                let body = typeof args[1]?.body === 'string' ? args[1].body : '';
                try { if (!body && args[0] instanceof Request) body = await args[0].clone().text(); } catch (_) {}
                const response = await originalFetch(...args);
                try {
                    if (body.includes('getLiveScoringStats')) {
                        response.clone().json().then(data => { window.__fantraxLiveScoring = data; });
                    }
                } catch (_) {}
                return response;
            };
        }""")
        cdp = context.new_cdp_session(page); cdp.send("Network.enable"); scoring_request_ids = []; observed = []
        def requested(event):
            request = event.get("request", {})
            if request.get("url", "").endswith("/fxpa/req") and "getLiveScoringStats" in request.get("postData", ""):
                scoring_request_ids.append(event["requestId"])
        cdp.on("Network.requestWillBeSent", requested)
        def observe(response):
            split=urlsplit(response.url)
            if split.hostname!="www.fantrax.com" or split.path!="/fxpa/req":return
            try:body=response.request.post_data_json
            except Exception:body=None
            observed.append((body,response))
        page.on("response",observe)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms); page.wait_for_timeout(8_000)
            if page.get_by_text("Login", exact=True).count(): raise RuntimeError("Fantrax authenticated session expired")
            browser_payload=page.evaluate("window.__fantraxLiveScoring")
            if browser_payload:return browser_payload
            scoring_response=next((response for body,response in observed if any(item.get("method")=="getLiveScoringStats" for item in (body or {}).get("msgs",[]))),None)
            if scoring_response is not None:
                try:return scoring_response.json()
                except Exception:pass
            if scoring_request_ids:
                body = cdp.send("Network.getResponseBody", {"requestId": scoring_request_ids[-1]})["body"]
                return json.loads(body)
            league_path=project_root/"data"/"raw"/"fantrax"/"2627"/"league"/"league_metadata_2627_latest.json"
            league=json.loads(league_path.read_text(encoding="utf-8")); period_obj=next((item for item in league.get("matchups",[]) if int(item.get("period",0))==int(period)),None)
            lines=page.locator("body").inner_text(); dom_rows=[]
            for index,item in enumerate((period_obj or {}).get("matchupList",[]),1):
                row={"matchup_id":str(item.get("id") or f"{int(period):02d}-{index:02d}")}
                for side in ("home","away"):
                    team=item[side];name=str(team["name"]); pattern=rf"(?m)^{re.escape(name)}[^\r\n]*\r?\n(-?\d+)(?:\r?\n(\.\d+))?"
                    found=re.search(pattern,lines)
                    if not found:raise RuntimeError(f"Structured Matchups DOM is missing score for {name}")
                    row[f"{side}_team_id"]=str(team["id"]);row[f"{side}_manager"]=name;row[f"{side}_score"]=float(found.group(1)+(found.group(2) or ""))
                dom_rows.append(row)
            if len(dom_rows)!=6:raise RuntimeError("Fantrax Matchups DOM did not contain six scheduled matchups")
            return {"_dom_matchups":dom_rows,"_all_events_finished":True}
        finally:
            context.close(); browser.close()


def commit_live_scoring(payload: dict, *, raw_root: Path, model_root: Path, season_id: str, period: int, acquired_at: str | None = None) -> dict:
    """Validate fully, then replace cache/model outputs; prior valid cache survives failure."""
    timestamp = acquired_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    dom_fallback="_dom_matchups" in payload
    if dom_fallback:
        rows=[]
        for item in payload["_dom_matchups"]:
            home=float(item["home_score"]);away=float(item["away_score"]);winner="TIE" if home==away else item["home_manager"] if home>away else item["away_manager"]
            rows.append({"season_id":season_id,"period":int(period),**item,"status":"completed" if payload.get("_all_events_finished") else "live","winner":winner,"margin":abs(home-away),"source":"Fantrax Matchups structured DOM fallback","acquired_at":timestamp,"maturity":"FINAL" if payload.get("_all_events_finished") else "LIVE"})
        matchups=pd.DataFrame(rows,columns=MATCHUP_COLUMNS);players=pd.DataFrame(columns=PLAYER_COLUMNS)
    else:matchups, players = normalize_live_scoring(payload, season_id=season_id, period=period, acquired_at=timestamp)
    folder = raw_root / "matchups" / f"period_{int(period):02d}"; folder.mkdir(parents=True, exist_ok=True)
    stage = raw_root / f".matchup_stage_{uuid4().hex[:8]}"; stage.mkdir()
    raw_name="matchup_dom.json" if dom_fallback else "live_scoring.json";raw_stage = stage / raw_name; raw_stage.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    match_stage = stage / "fantrax_matchups.csv"; matchups.to_csv(match_stage, index=False)
    player_stage = stage / "fantrax_live_player_scoring.csv"
    if not players.empty:players.to_csv(player_stage, index=False)
    checksum = hashlib.sha256(raw_stage.read_bytes()).hexdigest()
    prior_player=model_root/f"fantrax_live_player_scoring_{season_id}.csv";player_count=len(players) if not players.empty else len(pd.read_csv(prior_player)) if prior_player.exists() else 0
    metadata = {"season_id": season_id, "period": int(period), "matchup_rows": len(matchups), "team_coverage": 12, "player_rows": player_count, "acquired_at": timestamp, "checksum": checksum, "validation_status": "valid", "source": "Fantrax Matchups structured DOM fallback" if dom_fallback else "Fantrax getLiveScoringStats"}
    meta_stage = stage / "metadata.json"; meta_stage.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for staged in stage.iterdir(): staged.replace(folder / staged.name)
    stage.rmdir(); model_root.mkdir(parents=True, exist_ok=True)
    matchup_model=model_root/f"fantrax_matchups_{season_id}.csv"
    prior_matchups=pd.read_csv(matchup_model) if matchup_model.exists() else pd.DataFrame(columns=MATCHUP_COLUMNS)
    prior_matchups=prior_matchups[pd.to_numeric(prior_matchups.get("period"),errors="coerce").ne(int(period))]
    pd.concat([prior_matchups,matchups],ignore_index=True).sort_values(["period","matchup_id"],kind="stable").to_csv(matchup_model,index=False)
    if not players.empty:
        player_model=model_root/f"fantrax_live_player_scoring_{season_id}.csv"
        prior_players=pd.read_csv(player_model) if player_model.exists() else pd.DataFrame(columns=PLAYER_COLUMNS)
        prior_players=prior_players[pd.to_numeric(prior_players.get("period"),errors="coerce").ne(int(period))]
        pd.concat([prior_players,players],ignore_index=True).sort_values(["period","fantrax_team_id","fantrax_player_id"],kind="stable").to_csv(player_model,index=False)
    return metadata


def refresh_live_scoring(*, league_id: str, raw_root: Path, model_root: Path, season_id: str, period: int, project_root: Path) -> dict:
    payload = capture_live_scoring(league_id=league_id, period=period, project_root=project_root)
    return commit_live_scoring(payload, raw_root=raw_root, model_root=model_root, season_id=season_id, period=period)


def three_way_reconciliation(matchups: pd.DataFrame, live_players: pd.DataFrame, csv_players: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare official matchup, private player scoring, and detailed CSV states."""
    official_rows = []
    for row in matchups.to_dict("records"):
        for side in ("home", "away"):
            official_rows.append({"period": row["period"], "fantrax_team_id": str(row[f"{side}_team_id"]), "manager": row[f"{side}_manager"], "matchup_api_total": row[f"{side}_score"]})
    official = pd.DataFrame(official_rows)
    live_active = live_players[live_players.lineup_status.astype(str).str.upper().eq("ACTIVE")].copy()
    live_totals = live_active.groupby(["period", "fantrax_team_id"], as_index=False).live_scoring_fpts.sum(min_count=1).rename(columns={"live_scoring_fpts": "live_scoring_sum"})
    csv_status = csv_players.get("lineup_status", pd.Series(index=csv_players.index, dtype=str)).astype(str).str.upper()
    csv_active = csv_players[csv_status.isin({"ACTIVE", "ACT", "STARTER", "STARTING"})].copy()
    csv_active["fantrax_team_id"] = csv_active.get("current_manager_id").astype(str)
    csv_totals = csv_active.groupby(["period", "fantrax_team_id"], as_index=False).fantasy_points.sum(min_count=1).rename(columns={"fantasy_points": "manager_csv_active_sum"})
    managers = official.merge(live_totals, on=["period", "fantrax_team_id"], how="left").merge(csv_totals, on=["period", "fantrax_team_id"], how="left")
    managers["diff_matchup_vs_live"] = managers.matchup_api_total-managers.live_scoring_sum
    managers["diff_matchup_vs_csv"] = managers.matchup_api_total-managers.manager_csv_active_sum
    managers["diff_live_vs_csv"] = managers.live_scoring_sum-managers.manager_csv_active_sum
    managers["status"] = managers.apply(lambda row: "EXACT_ALL" if abs(row.diff_matchup_vs_live) <= .01 and abs(row.diff_matchup_vs_csv) <= .01 else "SOURCE_STATE_DIFFERENCE" if abs(row.diff_matchup_vs_live) <= .01 else "LIVE_SCORING_MISMATCH", axis=1)
    csv_player = csv_active[["period", "fantrax_team_id", "fantrax_player_id", "player_name", "fantasy_points"]].rename(columns={"fantasy_points": "csv_fpts"})
    players = live_active.merge(csv_player, on=["period", "fantrax_team_id", "fantrax_player_id"], how="outer", suffixes=("_live", "_csv"))
    players["player_name"] = players.get("player_name_live").combine_first(players.get("player_name_csv")); players["difference"] = pd.to_numeric(players.live_scoring_fpts, errors="coerce")-pd.to_numeric(players.csv_fpts, errors="coerce")
    players["status"] = players.difference.abs().le(.01).map({True: "match", False: "review"})
    return managers, players
