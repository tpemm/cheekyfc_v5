"""2026/27 League Hub consuming registered live-season datasets only."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from components.presentation import SHARED_COMPONENT_CSS, manager_card_html, metric_card, page_header, section_header
from core.models.data_result import DataStatus
from core.services.data_manager import DataManager, DatasetNotFoundError, DatasetValidationError, UnsupportedFormatError
from core.services.season_manager import SeasonManager
from fantrax.live.league_analytics import build_live_league_summary, compact_league_table, jester_history, latest_manager_of_month, league_highlights, scoring_frames


LIVE_DATASET_KEYS=("league_teams","league_standings","weekly_matchups","manager_week_summary","current_rosters","player_ownership","roster_change_events","live_manager_analytics","live_league_summary","live_position_strength","available_players","cup_configuration","cup_matchups")


def _load(data:DataManager,key:str,season_id:str,namespace:str,ui:Any)->pd.DataFrame:
    try: result=data.load_frame(key,season_id,namespace)
    except DatasetNotFoundError: return pd.DataFrame()
    except (DatasetValidationError,UnsupportedFormatError) as exc: ui.warning(str(exc)); return pd.DataFrame()
    if result.status in {DataStatus.MISSING,DataStatus.EMPTY}: return pd.DataFrame()
    return result.data.copy() if isinstance(result.data,pd.DataFrame) else pd.DataFrame()


def _number(value:Any,digits:int=1)->str:
    numeric=pd.to_numeric(pd.Series([value]),errors="coerce").iat[0]
    return "—" if pd.isna(numeric) else f"{numeric:,.{digits}f}"


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    source = frame[column] if column in frame else pd.Series(index=frame.index, dtype=float)
    return pd.to_numeric(source, errors="coerce")


@st.cache_data(show_spinner=False)
def build_live_hub_model(teams:pd.DataFrame,standings:pd.DataFrame,matchups:pd.DataFrame,weeks:pd.DataFrame)->dict[str,Any]:
    """Create presentation tables without changing historical analytical definitions."""
    periods = _numeric_column(standings, "period")
    latest_period = periods.max() if not periods.empty else np.nan
    latest = standings[periods.eq(latest_period)].copy() if pd.notna(latest_period) else standings.copy()
    if latest.empty and not teams.empty:
        latest=teams.rename(columns={"manager_name":"manager","fantasy_team_name":"team"}).copy(); latest["rank"]=pd.NA
    latest["rank"] = _numeric_column(latest, "rank")
    if "manager" not in latest:
        latest["manager"] = latest.get("manager_name", latest.get("team", ""))
    latest=latest.sort_values(["rank","manager"],na_position="last",kind="stable")
    week_frame=weeks.copy(); week_frame["period"]=pd.to_numeric(week_frame.get("period"),errors="coerce") if not week_frame.empty else pd.Series(dtype=float)
    latest_week=week_frame[week_frame["period"].eq(week_frame["period"].max())] if not week_frame.empty else week_frame
    manager_rows=[]
    for row in latest.to_dict("records"):
        manager=row.get("manager") or row.get("manager_name") or row.get("team")
        manager_weeks=week_frame[week_frame.get("manager",pd.Series(index=week_frame.index,dtype=object)).eq(manager)].sort_values("period")
        results="".join(manager_weeks.get("result",pd.Series(dtype=str)).dropna().astype(str).str.upper().tolist()[-5:])
        current_week=latest_week[latest_week.get("manager",pd.Series(index=latest_week.index,dtype=object)).eq(manager)]
        previous_rank=pd.NA
        if len(manager_weeks)>=2 and "rank_after_week" in manager_weeks: previous_rank=pd.to_numeric(manager_weeks.iloc[-2]["rank_after_week"],errors="coerce")
        current_rank=row.get("rank"); movement="—" if pd.isna(previous_rank) or pd.isna(current_rank) else f"{int(previous_rank)-int(current_rank):+d}"
        wins=int(pd.to_numeric(pd.Series([row.get("wins")]),errors="coerce").fillna(0).iat[0]); draws=int(pd.to_numeric(pd.Series([row.get("draws")]),errors="coerce").fillna(0).iat[0]); losses=int(pd.to_numeric(pd.Series([row.get("losses")]),errors="coerce").fillna(0).iat[0])
        average = _numeric_column(manager_weeks, "total_score").mean()
        manager_rows.append({"rank":int(current_rank) if pd.notna(current_rank) else "—","manager":manager,"team":row.get("team",""),"record":f"{wins}-{draws}-{losses}","form":" ".join(results) if results else "No form yet",
            "points_for":_number(row.get("fantasy_points_for")),"points_against":_number(row.get("fantasy_points_against")),"movement":movement,
            "weekly_score":_number(current_week["total_score"].iat[0]) if not current_week.empty and "total_score" in current_week else "—","average_score":_number(average), "average_score_numeric": average})
    managers=pd.DataFrame(manager_rows)
    completed=matchups[matchups.get("status",pd.Series(index=matchups.index,dtype=object)).astype(str).str.lower().eq("completed")].copy() if not matchups.empty else matchups.copy()
    highlights=[]
    if not week_frame.empty and pd.to_numeric(week_frame.get("total_score"),errors="coerce").notna().any():
        scores=pd.to_numeric(week_frame["total_score"],errors="coerce"); high=week_frame.loc[scores.idxmax()]; low=week_frame.loc[scores.idxmin()]
        highlights.extend([("Highest Score",high.get("manager"),f"GW {_number(high.get('period'), 0)} · {_number(high.get('total_score'))} pts"),("Lowest Score",low.get("manager"),f"GW {_number(low.get('period'), 0)} · {_number(low.get('total_score'))} pts"),("Manager of the Week",high.get("manager"),"Highest weekly score"),("Weekly Jester",low.get("manager"),"Lowest weekly score")])
    if not completed.empty:
        margins=pd.to_numeric(completed.get("margin"),errors="coerce"); closest=completed.loc[margins.idxmin()]; blowout=completed.loc[margins.idxmax()]
        highlights.extend([("Closest Match",f"{closest.get('home_manager')} vs {closest.get('away_manager')}",f"{_number(closest.get('margin'))}-point margin"),("Biggest Blowout",f"{blowout.get('home_manager')} vs {blowout.get('away_manager')}",f"{_number(blowout.get('margin'))}-point margin")])
    history=week_frame.pivot_table(index="period",columns="manager",values="rank_after_week",aggfunc="last") if not week_frame.empty and "rank_after_week" in week_frame else pd.DataFrame()
    scoring=week_frame.pivot_table(index="period",columns="manager",values="total_score",aggfunc="last") if not week_frame.empty else pd.DataFrame()
    return {"standings":latest,"managers":managers,"highlights":highlights,"position_history":history,"weekly_scoring":scoring}


def build_live_hub_model(teams:pd.DataFrame,standings:pd.DataFrame,matchups:pd.DataFrame,weeks:pd.DataFrame)->dict[str,Any]:
    """Build the Hub model from completed periods and stable identities."""
    periods=_numeric_column(standings,"period");latest_period=periods.max() if periods.notna().any() else np.nan
    latest=standings[periods.eq(latest_period)].copy() if pd.notna(latest_period) else standings.copy()
    if latest.empty and not teams.empty:
        latest=teams.rename(columns={"manager_name":"manager","fantasy_team_name":"team"}).copy();latest["rank"]=pd.NA
    identities=teams.copy()
    if identities.empty:identities=latest.rename(columns={"manager":"manager_name","team":"fantasy_team_name","rank":"current_rank"})
    seed=latest.rename(columns={"rank":"current_rank","manager":"manager_name","team":"fantasy_team_name","fantasy_points_for":"points_for","fantasy_points_against":"points_against"})
    summary=build_live_league_summary(identities,latest,weeks,seed)
    def column(name:str,default:Any=pd.NA)->pd.Series:return summary[name] if name in summary else pd.Series(default,index=summary.index)
    records=summary[[c for c in ("wins","draws","losses") if c in summary]].apply(pd.to_numeric,errors="coerce").fillna(0).astype(int).astype(str).agg("-".join,axis=1)
    managers=pd.DataFrame({"rank":column("current_rank"),"manager":column("manager_name"),"team":column("fantasy_team_name"),"record":records,"form":column("current_form").fillna("No form yet"),"points_for":column("points_for").map(_number),"points_against":column("points_against").map(_number),"movement":column("movement","\u2014"),"average_score":column("average_weekly_score").map(_number),"average_score_numeric":column("average_weekly_score")})
    scoring,history=scoring_frames(weeks);highlights=[(item["label"],item["value"],item["detail"]) for item in league_highlights(weeks,matchups)]
    return {"standings":latest,"summary":summary,"managers":managers,"highlights":highlights,"position_history":history,"weekly_scoring":scoring}


def render(season_id:str,*,data_manager:DataManager|None=None,season_manager:SeasonManager|None=None,ui:Any=st)->None:
    seasons=season_manager or SeasonManager(); season=seasons.context(season_id); namespace=seasons.resolve_namespace(season_id); data=data_manager or DataManager(season_manager=seasons)
    ui.markdown(SHARED_COMPONENT_CSS,unsafe_allow_html=True); page_header(ui,"League Hub","Live standings, form, scoring, and weekly league stories.",eyebrow="League overview",badge="2026/27 · Live")
    frames={key:_load(data,key,season_id,namespace,ui) for key in LIVE_DATASET_KEYS}
    if frames["league_standings"].empty and frames["league_teams"].empty:
        ui.info("Live league data is not available yet. Use Refresh League in Operations Center."); return
    model=build_live_hub_model(frames["league_teams"],frames["league_standings"],frames["weekly_matchups"],frames["manager_week_summary"])
    completed_periods=pd.to_numeric(frames["manager_week_summary"].get("period"),errors="coerce").dropna().nunique() if not frames["manager_week_summary"].empty else 0
    standings=model["standings"]
    cards=ui.columns(4,gap="small")
    jesters=jester_history(frames["manager_week_summary"]);latest_jester=jesters.sort_values("period").tail(1);counts=jesters.groupby(["manager_id","manager_name"],dropna=False).size().reset_index(name="count") if not jesters.empty else pd.DataFrame();leader_text="Season leader will appear after the first Jester is awarded." if counts.empty else ", ".join(counts[counts["count"].eq(counts["count"].max())]["manager_name"].astype(str));leader_detail="No awards yet" if counts.empty else f"{int(counts['count'].max())} Jester award(s)"
    motm=latest_manager_of_month(frames["manager_week_summary"]);motm_value="No Manager of the Month awarded yet" if motm is None else ", ".join(str(row["manager_name"]) for row in motm["leaders"]);motm_detail="Awaiting a completed calendar month" if motm is None else f"{motm['month']} · " + ", ".join(f"{row['wins']}-{row['draws']}-{row['losses']} · {row['points']:.1f} pts" for row in motm["leaders"])
    cup_config=frames["cup_configuration"];cup_matchups=frames["cup_matchups"];cfg=cup_config.iloc[0] if not cup_config.empty else pd.Series(dtype=object);cup_value="Planned" if cup_matchups.empty else "In progress";cup_detail=f"Next: GW{int(cfg.get('opening_round_week'))}" if pd.notna(cfg.get("opening_round_week")) else "Schedule pending"
    summary=(("Latest Jester","No Jester awarded yet" if latest_jester.empty else str(latest_jester.iloc[0].get("manager_name")),"Preseason" if latest_jester.empty else f"GW {int(latest_jester.iloc[0]['period'])} · {_number(latest_jester.iloc[0]['weekly_score'])} pts","gold"),("Jester Leader",leader_text,leader_detail,"red"),("Latest Manager of the Month",motm_value,motm_detail,"green"),("Cup Status",cup_value,cup_detail,"blue"))
    for column,(label,value,detail,tone) in zip(cards,summary):
        with column: metric_card(ui,label,value,detail,tone=tone)
    if not completed_periods:ui.info("Live scoring, form, luck, and weekly highlights will activate after the first completed scoring period.")
    section_header(ui,"League Table","Official Fantrax standings and scoring totals.")
    table=compact_league_table(model["summary"],frames["manager_week_summary"]);ui.dataframe(table,use_container_width=True,hide_index=True)
    section_header(ui,"League Highlights","Completed-week and matchup records; unavailable metrics stay blank.")
    if model["highlights"]:
        columns=ui.columns(3,gap="small")
        for index,(label,value,detail) in enumerate(model["highlights"]):
            with columns[index%3]: metric_card(ui,label,value,detail,tone="green" if index%2==0 else "gold")
    else: ui.info("Live weekly analytics will appear after the first completed scoring period.")
    section_header(ui,"League Position History","Rank after each completed scoring period.")
    if model["position_history"].empty: ui.info("League-position history will appear after the first completed scoring period.")
    else:
        history=model["position_history"].reset_index().melt("period",var_name="Manager",value_name="Rank").dropna()
        ui.vega_lite_chart(history,{"mark":{"type":"line","point":True},"encoding":{"x":{"field":"period","type":"ordinal","title":"Scoring Period"},"y":{"field":"Rank","type":"quantitative","scale":{"reverse":True},"title":"League Rank"},"color":{"field":"Manager","type":"nominal"},"tooltip":[{"field":"Manager"},{"field":"period","title":"Period"},{"field":"Rank"}]}},use_container_width=True)
    section_header(ui,"Weekly Scoring","Manager scores by scoring period.")
    if model["weekly_scoring"].empty: ui.info("Weekly scoring will appear after the first completed scoring period.")
    else: ui.line_chart(model["weekly_scoring"],use_container_width=True)
    managers=model["managers"]
    section_header(ui,"Leaderboards","Available live leaders and clearly labeled pending metrics.")
    boards=ui.columns(4,gap="small")
    available=[]
    if not managers.empty:
        average=managers.dropna(subset=["average_score_numeric"]).sort_values("average_score_numeric",ascending=False); available.append(("Highest Avg Score",average.iloc[0]["manager"] if not average.empty else "Awaiting scores","Live weekly average"))
        available.append(("Best Record",managers.iloc[0]["manager"],managers.iloc[0]["record"]))
    analytics=frames["live_manager_analytics"]
    if completed_periods and not analytics.empty and analytics.get("luck_wins",pd.Series(dtype=float)).notna().any():
        luckiest=analytics.loc[pd.to_numeric(analytics["luck_wins"],errors="coerce").idxmax()];available.append(("Luckiest Manager",luckiest.get("manager_name"),f"{luckiest.get('luck_wins'):+.1f} wins"))
    else:available.append(("Preseason Projection Leader",analytics.sort_values("current_roster_projection",ascending=False).iloc[0].get("fantasy_team_name") if not analytics.empty else "Awaiting rosters","Current Roster Projection"))
    if completed_periods and not analytics.empty and analytics.get("current_roster_ghost_per_90",pd.Series(dtype=float)).notna().any():
        ghost=analytics.loc[pd.to_numeric(analytics["current_roster_ghost_per_90"],errors="coerce").idxmax()];available.append(("Highest Current Ghost / 90",ghost.get("manager_name"),_number(ghost.get("current_roster_ghost_per_90"))))
    else:available.append(("Draft Retention Leader",analytics.sort_values("draft_retention_pct",ascending=False).iloc[0].get("fantasy_team_name") if not analytics.empty else "Awaiting rosters","Neutral roster context"))
    for column,item in zip(boards,available):
        with column: metric_card(ui,*item)
    section_header(ui,"Recent Roster Activity","Verified changes observed between distinct roster snapshots.")
    activity=frames["roster_change_events"].copy()
    visible={"PLAYER_ADDED","PLAYER_DROPPED","MOVED_TO_RESERVE","MOVED_TO_IR","RETURNED_FROM_IR"}
    activity=activity[activity.get("event_type",pd.Series(index=activity.index,dtype=object)).isin(visible)]
    if activity.empty:
        ui.info("No roster changes detected since the initial 2026/27 snapshot.")
    else:
        counts=activity["event_type"].value_counts();ui.caption(f"Adds: {int(counts.get('PLAYER_ADDED',0))} \u00b7 Drops: {int(counts.get('PLAYER_DROPPED',0))} \u00b7 Verified changes: {len(activity)}")
        activity=activity.sort_values("detected_at",ascending=False).head(10)
        display=activity.rename(columns={"detected_at":"Observed","event_type":"Change","player_name":"Player","previous_manager_name":"Previous Manager","new_manager_name":"New Manager"})
        ui.dataframe(display[[column for column in ("Observed","Change","Player","Previous Manager","New Manager") if column in display]],use_container_width=True,hide_index=True)
    section_header(ui,"Current Roster Projections","Preseason roster context from the canonical live manager dataset.")
    manager_analytics=frames["live_manager_analytics"]
    if manager_analytics.empty: ui.info("Roster projections will appear after the next live build.")
    else:
        projection=manager_analytics.sort_values("current_roster_projection",ascending=False,na_position="last")
        ui.dataframe(projection[[c for c in ("fantasy_team_name","current_roster_projection","historical_points_per_90","current_roster_points_per_90","current_roster_ghost_per_90","draft_retention_pct","roster_change_count") if c in projection]],hide_index=True,use_container_width=True)
    section_header(ui,"Strongest Current Position Groups","Canonical-position assignments; each player counts once.")
    groups=frames["live_position_strength"].sort_values(["position_group","league_rank"],na_position="last") if not frames["live_position_strength"].empty else pd.DataFrame()
    if groups.empty: ui.info("Position strength will appear after the next live build.")
    else:
        labels=frames["live_manager_analytics"][[c for c in ("manager_id","manager_name","fantasy_team_name") if c in frames["live_manager_analytics"]]].drop_duplicates("manager_id");leaders=groups[groups["league_rank"].eq(1)].merge(labels,on="manager_id",how="left");leaders["Manager / Team"]=leaders["fantasy_team_name"].fillna(leaders["manager_name"]);leaders["Basis"]="Draft / Projection Basis";leaders=leaders.rename(columns={"position_group":"Position Group","league_rank":"League Rank","raw_value":"Supporting Value"})
        ui.dataframe(leaders[[c for c in ("Position Group","Manager / Team","League Rank","Supporting Value","Basis") if c in leaders]],hide_index=True,use_container_width=True)
    section_header(ui,"Available Players","Free agents using labeled draft, projection, historical, and supported current facts; no waiver score.")
    free=frames["available_players"].copy()
    if free.empty: ui.info("No available-player model is loaded.")
    else:
        free["draft_score"]=pd.to_numeric(free.get("draft_score"),errors="coerce")
        ui.dataframe(free.sort_values("draft_score",ascending=False,na_position="last")[[c for c in ("player_name","fantrax_position","premier_league_club","draft_rank","draft_score","fantrax_projected_points","historical_points_per_90","historical_ghost_per_90","historical_xgi_per_90","current_points_per_start","current_ghost_per_start") if c in free]].head(10),hide_index=True,use_container_width=True)
