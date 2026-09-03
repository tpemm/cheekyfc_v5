"""Reusable, cache-only league-level analytics for the live League Hub."""
from __future__ import annotations
from typing import Any
import json
from pathlib import Path
import numpy as np
import pandas as pd


def completed_manager_weeks(frame:pd.DataFrame)->pd.DataFrame:
    if frame.empty:return frame.copy()
    score="fantasy_points" if "fantasy_points" in frame else "total_score"
    output=frame.copy();output["period"]=pd.to_numeric(output.get("period"),errors="coerce");output[score]=pd.to_numeric(output.get(score),errors="coerce")
    if "result" in output:output=output[output["result"].notna()]
    return output.dropna(subset=["period",score]).sort_values(["period","manager_id"] if "manager_id" in output else ["period"])


def format_movement(current:Any,previous:Any)->str:
    current=pd.to_numeric(current,errors="coerce");previous=pd.to_numeric(previous,errors="coerce")
    if pd.isna(current) or pd.isna(previous):return "\u2014"
    change=int(previous)-int(current)
    return f"\u25b2{change}" if change>0 else f"\u25bc{abs(change)}" if change<0 else "\u2014"


def build_live_league_summary(teams:pd.DataFrame,standings:pd.DataFrame,weeks:pd.DataFrame,managers:pd.DataFrame)->pd.DataFrame:
    """One row per manager; reuse manager analytics and add league-table context."""
    base=managers.copy() if not managers.empty else teams.copy()
    if base.empty:return pd.DataFrame()
    if not teams.empty and "manager_id" in base and "manager_id" in teams:
        current=teams.drop_duplicates("manager_id").set_index(teams.drop_duplicates("manager_id").manager_id.astype(str))
        ids=base.manager_id.astype(str)
        for column in ("manager_name","fantasy_team_name","fantasy_team_id"):
            if column in current:base[column]=ids.map(current[column]).fillna(base.get(column))
    complete=completed_manager_weeks(weeks);rows=[]
    for manager in base.to_dict("records"):
        manager_id=str(manager.get("manager_id"));name=manager.get("manager_name")
        own=complete[complete.get("manager_id",pd.Series(index=complete.index,dtype=object)).astype(str).eq(manager_id)] if "manager_id" in complete else complete[complete.get("manager",pd.Series(index=complete.index,dtype=object)).eq(name)]
        if "period" in own:own=own.sort_values("period")
        current_rank=own.iloc[-1].get("rank_after_week") if not own.empty else manager.get("current_rank",manager.get("rank"))
        previous_rank=own.iloc[-2].get("rank_after_week") if len(own)>=2 else pd.NA
        results=own.get("result",pd.Series(dtype=object)).dropna().astype(str).str.upper().tail(5).tolist()
        score_col="fantasy_points" if "fantasy_points" in own else "total_score"
        scores=pd.to_numeric(own.get(score_col),errors="coerce").dropna() if score_col in own else pd.Series(dtype=float)
        wins=int(own.get("result",pd.Series(dtype=object)).eq("W").sum());draws=int(own.get("result",pd.Series(dtype=object)).isin(["D","T"]).sum());losses=int(own.get("result",pd.Series(dtype=object)).eq("L").sum())
        row=dict(manager);row.update({"wins":wins,"draws":draws,"losses":losses,"current_rank":current_rank,"previous_rank":previous_rank,"rank_change":pd.to_numeric(previous_rank,errors="coerce")-pd.to_numeric(current_rank,errors="coerce"),"movement":format_movement(current_rank,previous_rank),"current_form":" ".join("T" if value=="D" else value for value in results) if results else pd.NA,"average_weekly_score":scores.mean(),"median_weekly_score":scores.median(),"scoring_std_dev":scores.std(),"high_score":scores.max(),"low_score":scores.min()})
        rows.append(row)
    result=pd.DataFrame(rows)
    return result.sort_values("current_rank",kind="stable",na_position="last").reset_index(drop=True)


def completed_matchups(frame:pd.DataFrame)->pd.DataFrame:
    if frame.empty:return frame.copy()
    output=frame.copy();home=pd.to_numeric(output.get("home_score",pd.Series(index=output.index,dtype=float)),errors="coerce");away=pd.to_numeric(output.get("away_score",pd.Series(index=output.index,dtype=float)),errors="coerce");period=pd.to_numeric(output.get("period",pd.Series(index=output.index,dtype=float)),errors="coerce");margin=pd.to_numeric(output.get("margin",pd.Series(index=output.index,dtype=float)),errors="coerce")
    status=output.get("status",pd.Series(index=output.index,dtype=object)).astype(str).str.lower()
    complete_status=status.isin({"completed","final","complete"});mask=complete_status&((home.notna()&away.notna())|margin.notna())
    output=output[mask].copy();output["margin"]=(home[mask]-away[mask]).abs().fillna(margin[mask].abs());return output


def league_highlights(weeks:pd.DataFrame,matchups:pd.DataFrame)->list[dict[str,Any]]:
    complete=completed_manager_weeks(weeks);games=completed_matchups(matchups)
    if complete.empty:return []
    score="fantasy_points" if "fantasy_points" in complete else "total_score";latest_period=complete["period"].max();latest=complete[complete["period"].eq(latest_period)];scores=pd.to_numeric(latest[score],errors="coerce")
    high=latest.loc[scores.idxmax()];low=latest.loc[scores.idxmin()];manager_key="manager_name" if "manager_name" in latest else "manager"
    result=[{"label":"Manager of the Week","value":high.get(manager_key),"detail":f"GW {int(latest_period)} \u00b7 {high.get(score):.1f} pts"},{"label":"Weekly Jester","value":low.get(manager_key),"detail":f"GW {int(latest_period)} \u00b7 {low.get(score):.1f} pts"},{"label":"Highest Score","value":high.get(manager_key),"detail":f"GW{int(latest_period)} \u00b7 {high.get(score):.1f} pts"},{"label":"Lowest Score","value":low.get(manager_key),"detail":f"GW{int(latest_period)} \u00b7 {low.get(score):.1f} pts"}]
    if not games.empty:
        closest=games.loc[games["margin"].idxmin()];blowout=games.loc[games["margin"].idxmax()]
        def matchup(row:pd.Series)->tuple[str,str]:
            home_score=pd.to_numeric(row.get("home_score"),errors="coerce");away_score=pd.to_numeric(row.get("away_score"),errors="coerce")
            if pd.isna(home_score) or pd.isna(away_score):return f"{row.get('home_manager')} vs {row.get('away_manager')}",f"{row.margin:.1f}-point margin"
            home_win=home_score>away_score;tie=home_score==away_score
            marker=" (T)" if tie else " (W)"
            winner=row.get("home_manager") if home_win or tie else row.get("away_manager");winner_score=home_score if home_win or tie else away_score
            loser=row.get("away_manager") if home_win or tie else row.get("home_manager");loser_score=away_score if home_win or tie else home_score
            period=pd.to_numeric(row.get("period"),errors="coerce");gw=f"GW{int(period)} \u00b7 " if pd.notna(period) else ""
            return f"{winner} {winner_score:.1f}{marker}",f"vs {loser} {loser_score:.1f} \u00b7 {gw}{row.margin:.1f}-point margin"
        closest_value,closest_detail=matchup(closest);blowout_value,blowout_detail=matchup(blowout)
        result.extend([{"label":"Closest Match","value":closest_value,"detail":closest_detail},{"label":"Biggest Blowout","value":blowout_value,"detail":blowout_detail}])
    return result


def scoring_frames(weeks:pd.DataFrame)->tuple[pd.DataFrame,pd.DataFrame]:
    complete=completed_manager_weeks(weeks)
    if complete.empty:return pd.DataFrame(),pd.DataFrame()
    manager="manager_name" if "manager_name" in complete else "manager";score="fantasy_points" if "fantasy_points" in complete else "total_score"
    scoring=complete.pivot_table(index="period",columns=manager,values=score,aggfunc="last");scoring["League Average"]=complete.groupby("period")[score].mean()
    history=complete.pivot_table(index="period",columns=manager,values="rank_after_week",aggfunc="last") if "rank_after_week" in complete else pd.DataFrame()
    return scoring,history


def jester_history(weeks:pd.DataFrame)->pd.DataFrame:
    complete=completed_manager_weeks(weeks)
    columns=("period","manager_id","manager_name","fantasy_team_name","weekly_score","awarded")
    if complete.empty:return pd.DataFrame(columns=columns)
    score="fantasy_points" if "fantasy_points" in complete else "total_score";rows=[]
    for period,group in complete.groupby("period"):
        values=pd.to_numeric(group[score],errors="coerce");minimum=values.min()
        for _,row in group[values.eq(minimum)].iterrows():rows.append({"period":period,"manager_id":row.get("manager_id"),"manager_name":row.get("manager_name",row.get("manager")),"fantasy_team_name":row.get("fantasy_team_name"),"weekly_score":minimum,"awarded":True})
    return pd.DataFrame(rows,columns=columns)


def latest_manager_of_month(weeks:pd.DataFrame,*,as_of:object=None)->dict[str,Any]|None:
    """Best monthly record, then points; award only a completed calendar month."""
    complete=completed_manager_weeks(weeks)
    date_col=next((c for c in ("period_completed_at","completed_at","period_end") if c in complete),None)
    if complete.empty or date_col is None:return None
    complete["_date"]=pd.to_datetime(complete[date_col],errors="coerce",utc=True);complete=complete.dropna(subset=["_date"])
    today=pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC")
    if today.tzinfo is None:today=today.tz_localize("UTC")
    complete["_month"]=complete["_date"].dt.tz_convert(None).dt.to_period("M").astype(str);current=today.tz_convert(None).to_period("M").strftime("%Y-%m");complete=complete[complete["_month"].ne(current)]
    if complete.empty:return None
    month=complete["_month"].max();part=complete[complete["_month"].eq(month)].copy();score="fantasy_points" if "fantasy_points" in part else "total_score"
    if "fantasy_team_name" not in part:part["fantasy_team_name"]=part.get("manager_name",part.get("manager"))
    part["_win"]=part.get("result",pd.Series(index=part.index,dtype=object)).eq("W").astype(int);part["_draw"]=part.get("result",pd.Series(index=part.index,dtype=object)).eq("D").astype(int);part["_loss"]=part.get("result",pd.Series(index=part.index,dtype=object)).eq("L").astype(int)
    grouped=part.groupby(["manager_id","manager_name","fantasy_team_name"],dropna=False).agg(wins=("_win","sum"),draws=("_draw","sum"),losses=("_loss","sum"),points=(score,"sum")).reset_index().sort_values(["wins","draws","losses","points"],ascending=[False,False,True,False],kind="stable")
    best=grouped.iloc[0];tied=grouped[(grouped.wins.eq(best.wins))&(grouped.draws.eq(best.draws))&(grouped.losses.eq(best.losses))&(grouped.points.eq(best.points))]
    return {"month":month,"leaders":tied.to_dict("records")}


def configured_manager_of_month(weeks:pd.DataFrame,*,as_of:object=None,config_path:Path|None=None)->dict[str,Any]|None:
    """Current configured award race; a winner exists only after period close."""
    path=config_path or Path(__file__).resolve().parents[2]/"config"/"league_award_periods_2627.json"
    if not path.exists():return None
    config=json.loads(path.read_text(encoding="utf-8"));today=pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC"))
    if today.tzinfo is None:today=today.tz_localize("UTC")
    periods=config.get("manager_of_month",[]);chosen=next((p for p in periods if pd.Timestamp(p["start_date"],tz="UTC")<=today<=pd.Timestamp(p["end_date"],tz="UTC")+pd.Timedelta(days=1)),periods[0] if periods else None)
    if chosen is None:return None
    complete=completed_manager_weeks(weeks).copy();date_col=next((c for c in ("period_completed_at","completed_at","period_end") if c in complete),None)
    if date_col:complete["_date"]=pd.to_datetime(complete[date_col],errors="coerce",utc=True);complete=complete[complete._date.between(pd.Timestamp(chosen["start_date"],tz="UTC"),pd.Timestamp(chosen["end_date"],tz="UTC")+pd.Timedelta(days=1),inclusive="left")]
    if complete.empty:return {**chosen,"completion_state":"in progress","current_leaders":[],"winner":None,"included_completed_gws":[]}
    score="fantasy_points" if "fantasy_points" in complete else "total_score";complete["_win"]=complete.result.eq("W").astype(int);complete["_draw"]=complete.result.isin(["D","T"]).astype(int);complete["_loss"]=complete.result.eq("L").astype(int)
    grouped=complete.groupby(["manager_id","manager_name"],dropna=False).agg(wins=("_win","sum"),draws=("_draw","sum"),losses=("_loss","sum"),points=(score,"sum")).reset_index().sort_values(["wins","draws","losses","points"],ascending=[False,False,True,False],kind="stable")
    best=grouped.iloc[0];leaders=grouped[(grouped.wins.eq(best.wins))&(grouped.draws.eq(best.draws))&(grouped.losses.eq(best.losses))&(grouped.points.eq(best.points))].to_dict("records")
    closed=today>pd.Timestamp(chosen["end_date"],tz="UTC")+pd.Timedelta(days=1)
    return {**chosen,"completion_state":"complete" if closed else "in progress","current_leaders":leaders,"winner":leaders if closed else None,"included_completed_gws":sorted(pd.to_numeric(complete.period,errors="coerce").dropna().astype(int).unique().tolist())}


LIVE_TABLE_COLUMNS=("Rank","Team","Movement","Record","Form","Pts / GW","Ghost / GW","Efficiency","Lineup Changes")


def compact_league_table(summary:pd.DataFrame,weeks:pd.DataFrame)->pd.DataFrame:
    rows=[];complete=completed_manager_weeks(weeks)
    for manager in summary.to_dict("records"):
        manager_id=str(manager.get("manager_id"));own=complete[complete.get("manager_id",pd.Series(index=complete.index,dtype=object)).astype(str).eq(manager_id)] if not complete.empty else complete
        periods=own["period"].nunique() if not own.empty else 0
        ghost=pd.to_numeric(own.get("ghost_points"),errors="coerce") if "ghost_points" in own else pd.Series(dtype=float);ghost_rate=ghost.sum()/periods if periods and len(ghost)==len(own) and ghost.notna().all() else pd.NA
        efficiency=pd.to_numeric(own.get("lineup_efficiency_pct"),errors="coerce").mean() if "lineup_efficiency_pct" in own and own["lineup_efficiency_pct"].notna().all() and not own.empty else pd.NA
        changes=pd.to_numeric(own.get("lineup_changes"),errors="coerce").sum() if "lineup_changes" in own and own["lineup_changes"].notna().all() and not own.empty else pd.NA
        def count(key:str)->int:
            value=pd.to_numeric(manager.get(key),errors="coerce");return 0 if pd.isna(value) else int(value)
        record=f"{count('wins')}-{count('draws')}-{count('losses')}"
        rows.append({"Rank":manager.get("current_rank"),"Team":manager.get("fantasy_team_name") or manager.get("manager_name"),"Movement":manager.get("movement","\u2014"),"Record":record,"Form":manager.get("current_form") if periods else pd.NA,"Pts / GW":pd.to_numeric(manager.get("average_weekly_score"),errors="coerce") if periods else pd.NA,"Ghost / GW":ghost_rate,"Efficiency":efficiency,"Lineup Changes":changes})
    return pd.DataFrame(rows,columns=LIVE_TABLE_COLUMNS)


def player_leaderboards(weekly:pd.DataFrame,*,include_live:bool=False)->dict[str,pd.DataFrame]:
    """Top-three current player facts, including an explicitly live period."""
    names=("Golden Boot","Playmaker","Golden Glove","Highest Weekly Points")
    if weekly.empty:return {name:pd.DataFrame() for name in names}
    frame=weekly.copy()
    if not include_live and "period_complete" in frame:frame=frame[frame.period_complete.fillna(False).astype(bool)]
    if frame.empty:return {name:pd.DataFrame() for name in names}
    player="player_name" if "player_name" in frame else "canonical_name";manager=next((column for column in ("fantasy_team_name","manager_name") if column in frame),None)
    def season(metric:str,label:str)->pd.DataFrame:
        if metric not in frame:return pd.DataFrame()
        groups=[player]+([manager] if manager else []);result=frame.assign(_value=pd.to_numeric(frame[metric],errors="coerce")).groupby(groups,as_index=False)["_value"].sum(min_count=1).dropna().sort_values(["_value",player],ascending=[False,True],kind="stable")
        result["Rank"]=result["_value"].rank(method="min",ascending=False).astype(int);result["Tie Count"]=result.groupby("_value")["_value"].transform("size");result=result[result["Rank"].le(3)].head(3).reset_index(drop=True)
        rename={player:"Player","_value":label};rename.update({manager:"Manager"} if manager else {});return result.rename(columns=rename)
    points=frame.assign(_value=pd.to_numeric(frame.get("fantrax_points",frame.get("fantasy_points")),errors="coerce"),_period=pd.to_numeric(frame.get("period"),errors="coerce")).dropna(subset=["_value","_period"]).sort_values(["_value",player],ascending=[False,True],kind="stable");points["Rank"]=points["_value"].rank(method="min",ascending=False).astype(int);points["Tie Count"]=points.groupby("_value")["_value"].transform("size");points=points[points.Rank.le(3)].head(3).reset_index(drop=True)
    point_columns=["Rank",player]+([manager] if manager else [])+["_period","_value","Tie Count"];rename={player:"Player","_period":"GW","_value":"Fantasy Points"};rename.update({manager:"Manager"} if manager else {});points=points[point_columns].rename(columns=rename)
    return {"Golden Boot":season("goals","Goals"),"Playmaker":season("assists","Assists"),"Golden Glove":season("clean_sheets","Clean Sheets"),"Highest Weekly Points":points}


def manager_active_season_totals(active_weekly:pd.DataFrame)->pd.DataFrame:
    """Cumulative completed-period production attributed to its historical manager."""
    columns=("season_id","manager_id","manager_name","fantasy_team_name","periods_counted","active_starts","goals","assists","clean_sheets","ghost_points")
    if active_weekly.empty:return pd.DataFrame(columns=columns)
    frame=active_weekly.copy()
    if "period_complete" in frame:frame=frame[frame.period_complete.fillna(False).astype(bool)]
    if "active_start" in frame:frame=frame[frame.active_start.fillna(False).astype(bool)]
    frame=frame[frame.get("manager_id",pd.Series(index=frame.index,dtype=object)).notna()]
    if frame.empty:return pd.DataFrame(columns=columns)
    keys=[column for column in ("season_id","manager_id") if column in frame]
    for metric in ("goals","assists","clean_sheets","ghost_points"):frame[metric]=pd.to_numeric(frame.get(metric),errors="coerce")
    grouped=frame.groupby(keys,dropna=False)
    result=grouped.agg(periods_counted=("period","nunique"),active_starts=("fantrax_player_id","size"),goals=("goals",lambda values:values.sum(min_count=1)),assists=("assists",lambda values:values.sum(min_count=1)),clean_sheets=("clean_sheets",lambda values:values.sum(min_count=1)),ghost_points=("ghost_points",lambda values:values.sum(min_count=len(values)))).reset_index()
    labels=frame.sort_values("period",kind="stable").groupby(keys,dropna=False).tail(1)[[*keys,*[c for c in ("manager_name","fantasy_team_name") if c in frame]]]
    result=result.merge(labels,on=keys,how="left")
    if "season_id" not in result:result["season_id"]=pd.NA
    if "fantasy_team_name" not in result:result["fantasy_team_name"]=result.get("manager_name")
    return result.reindex(columns=columns).sort_values("manager_id",kind="stable").reset_index(drop=True)


def manager_award_leaderboards(totals:pd.DataFrame,*,display_limit:int=3)->dict[str,pd.DataFrame]:
    """Competition-ranked manager awards with compact, disclosed large ties."""
    awards={"Golden Boot":("goals","Goals"),"Playmaker":("assists","Assists"),"Golden Glove":("clean_sheets","Clean Sheets"),"Ghost King":("ghost_points","Ghost Points")};output={}
    for label,(metric,display) in awards.items():
        if totals.empty or metric not in totals:output[label]=pd.DataFrame();continue
        frame=totals.assign(_value=pd.to_numeric(totals[metric],errors="coerce")).dropna(subset=["_value"]).copy()
        frame["Rank"]=frame["_value"].rank(method="min",ascending=False).astype(int);frame["Tie Count"]=frame.groupby("_value")["_value"].transform("size")
        frame=frame[frame.Rank.le(3)].sort_values(["Rank","manager_name","manager_id"],kind="stable")
        selected=frame.head(display_limit).copy();selected["Hidden Ties"]=(selected["Tie Count"]-selected.groupby(["Rank","_value"])["manager_id"].transform("size")).clip(lower=0)
        output[label]=selected[["Rank","manager_id","manager_name","fantasy_team_name","_value","Tie Count","Hidden Ties"]].rename(columns={"manager_name":"Manager","fantasy_team_name":"Fantasy Team","_value":display}).reset_index(drop=True)
    return output
