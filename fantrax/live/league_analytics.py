"""Reusable, cache-only league-level analytics for the live League Hub."""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd


def completed_manager_weeks(frame:pd.DataFrame)->pd.DataFrame:
    if frame.empty:return frame.copy()
    score="fantasy_points" if "fantasy_points" in frame else "total_score"
    output=frame.copy();output["period"]=pd.to_numeric(output.get("period"),errors="coerce");output[score]=pd.to_numeric(output.get(score),errors="coerce")
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
    complete=completed_manager_weeks(weeks);rows=[]
    for manager in base.to_dict("records"):
        manager_id=str(manager.get("manager_id"));name=manager.get("manager_name")
        own=complete[complete.get("manager_id",pd.Series(index=complete.index,dtype=object)).astype(str).eq(manager_id)] if "manager_id" in complete else complete[complete.get("manager",pd.Series(index=complete.index,dtype=object)).eq(name)]
        if "period" in own:own=own.sort_values("period")
        current_rank=manager.get("current_rank",manager.get("rank"));previous_rank=own.iloc[-2].get("rank_after_week") if len(own)>=2 else pd.NA
        results=own.get("result",pd.Series(dtype=object)).dropna().astype(str).str.upper().tail(5).tolist()
        score_col="fantasy_points" if "fantasy_points" in own else "total_score"
        scores=pd.to_numeric(own.get(score_col),errors="coerce").dropna() if score_col in own else pd.Series(dtype=float)
        row=dict(manager);row.update({"current_rank":current_rank,"previous_rank":previous_rank,"rank_change":pd.to_numeric(previous_rank,errors="coerce")-pd.to_numeric(current_rank,errors="coerce"),"movement":format_movement(current_rank,previous_rank),"current_form":" ".join(results) if results else pd.NA,"average_weekly_score":scores.mean(),"median_weekly_score":scores.median(),"scoring_std_dev":scores.std(),"high_score":scores.max(),"low_score":scores.min()})
        rows.append(row)
    return pd.DataFrame(rows)


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
    result=[{"label":"Manager of the Week","value":high.get(manager_key),"detail":f"GW {int(latest_period)} \u00b7 {high.get(score):.1f} pts"},{"label":"Weekly Jester","value":low.get(manager_key),"detail":f"GW {int(latest_period)} \u00b7 {low.get(score):.1f} pts"},{"label":"Highest Score","value":high.get(manager_key),"detail":"This Week"},{"label":"Lowest Score","value":low.get(manager_key),"detail":"This Week"}]
    if not games.empty:
        closest=games.loc[games["margin"].idxmin()];blowout=games.loc[games["margin"].idxmax()]
        def detail(row:pd.Series)->str:
            period=pd.to_numeric(row.get("period"),errors="coerce");prefix=f"GW {int(period)} \u00b7 " if pd.notna(period) else ""
            return f"{prefix}{row.get('margin'):.1f}-point margin"
        result.extend([{"label":"Closest Match","value":f"{closest.get('home_manager')} vs {closest.get('away_manager')}","detail":detail(closest)},{"label":"Biggest Blowout","value":f"{blowout.get('home_manager')} vs {blowout.get('away_manager')}","detail":detail(blowout)}])
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
