"""Current-first, model-only Teams research experience."""
from __future__ import annotations
from typing import Any
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics.teams.research import EVENT_LAYERS,prepare_team_events,prepare_team_fantasy_matchups,prepare_team_historical_comparison,prepare_team_match_analysis,prepare_team_overview,prepare_team_profile_percentiles,prepare_team_tactical_profile
from analytics.teams.soccerdata import next_five_elo_context
from analytics.teams.tactical import DEFAULT_METHODOLOGY_PATH,fingerprint_records,load_methodology
from components.player_pitch import add_points,draw_pitch
from components.presentation import page_header,section_header
from core.services.data_manager import DataManager
from core.services.historical_advanced import get_historical_team_advanced,historical_club_id

CURRENT="2026/27 Current"; HISTORICAL="2025/26 Historical"
TABS=("Overview","Match Analysis","Tactical Profile","Fantasy Matchups")
DATASET_KEYS=("premier_league_clubs","team_fixtures","team_match_analytics","team_season_profile","team_manager_profile","team_formation_analytics","team_home_away_profile","team_fantasy_allowed_match","team_fantasy_allowed_position_match","whoscored_event")
ROLE_COORDINATES={"GK":(50,8),"LB":(15,28),"LWB":(10,42),"CB":(50,25),"RB":(85,28),"RWB":(90,42),"DM":(50,42),"LM":(18,57),"CM":(50,57),"RM":(82,57),"LW":(15,75),"CAM":(50,72),"RW":(85,75),"ST":(50,90)}

# Kept as compatibility helpers for existing fixture/formation consumers.
def formation_pitch_figure(usage:pd.DataFrame)->go.Figure:
    leaders=usage.sort_values(["actual_tactical_role","role_rank"]).groupby("actual_tactical_role").head(2);labels=[];xs=[];ys=[]
    for role,group in leaders.groupby("actual_tactical_role",sort=False):
        x,y=ROLE_COORDINATES.get(str(role),(50,50));xs.append(x);ys.append(y);labels.append(f"<b>{role}</b><br>"+"<br>".join(f"{r.player_name} — {int(r.role_starts)}" for _,r in group.iterrows()))
    fig=go.Figure(go.Scatter(x=xs,y=ys,text=labels,mode="markers+text",textposition="top center",marker={"size":18,"color":"#1f7a4d"},hoverinfo="text"));fig.update_xaxes(range=[0,100],visible=False);fig.update_yaxes(range=[0,100],visible=False,scaleanchor="x");fig.update_layout(height=600,margin=dict(l=10,r=10,t=25,b=10));return fig

def directory_frame(clubs:pd.DataFrame,fixtures:pd.DataFrame,*,now:Any=None)->pd.DataFrame:
    current=pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now,utc=True);future=fixtures[fixtures.get("competition_type",pd.Series(index=fixtures.index,dtype=object)).eq("league")].copy();future["_kickoff"]=pd.to_datetime(future.get("kickoff_time"),errors="coerce",utc=True);future=future[future._kickoff.ge(current)].sort_values("_kickoff").drop_duplicates("club_id");lookup=future.set_index("club_id") if not future.empty else pd.DataFrame();out=clubs[["canonical_club_id","canonical_name","short_name","abbreviation"]].copy();out["Next Fixture"]=out.canonical_club_id.map(lookup["opponent"] if not lookup.empty else {});out["H/A"]=out.canonical_club_id.map(lookup["home_away"] if not lookup.empty else {});return out.rename(columns={"canonical_name":"Club","abbreviation":"Code"})

def squad_frame(players:pd.DataFrame,fantrax_code:str)->pd.DataFrame:
    squad=players[players.get("premier_league_club",pd.Series(index=players.index,dtype=object)).eq(fantrax_code)].copy();columns={"player_name":"Player","fantrax_position":"Position","current_manager_name":"Owner","current_points_per_start":"Points / Start","current_ghost_per_start":"Ghost / Start","current_xgi_per_90":"xGI / 90","projected_minutes_percentage":"Minutes Outlook"};return squad.reindex(columns=columns).rename(columns=columns).sort_values("Player")

def fixture_frame(fixtures:pd.DataFrame,club_id:str)->pd.DataFrame:
    rows=fixtures[fixtures.club_id.eq(club_id)].copy();rows["Result / Status"]=rows.apply(lambda r:f"{r.goals_for}-{r.goals_against}" if bool(r.completed) else r.status,axis=1);columns={"date":"Date","competition":"Competition","opponent":"Opponent","home_away":"H/A","fantrax_period":"Fantrax Period"};return rows.sort_values("kickoff_time").rename(columns=columns).reindex(columns=[*columns.values(),"Result / Status"])

def team_elo_context(club_id:str,fixtures:pd.DataFrame,elo:pd.DataFrame,*,now:Any=None)->dict[str,Any]:
    current=elo[elo.get("canonical_club_id",pd.Series(index=elo.index,dtype=object)).eq(club_id)].head(1);next_five=next_five_elo_context(fixtures,elo,club_id,now=now);own=pd.NA if current.empty else current.iloc[0].get("elo");rank=pd.NA if current.empty else current.iloc[0].get("elo_rank_pl");opponent=pd.NA if next_five.empty else next_five.iloc[0].get("opponent_elo");return {"elo":own,"elo_rank_pl":rank,"next_opponent_elo":opponent,"next_opponent_elo_difference":pd.NA if pd.isna(own) or pd.isna(opponent) else float(own)-float(opponent),"next_five":next_five}

def _load(data:DataManager,key:str,season:str,working:bool=False)->pd.DataFrame:
    try:r=data.load_frame(key,season,"working") if working else data.load(key,season);return r.data.copy() if isinstance(r.data,pd.DataFrame) else pd.DataFrame()
    except Exception:return pd.DataFrame()

def _fmt(value:object,n:int=1,signed:bool=False)->str:
    x=pd.to_numeric(value,errors="coerce")
    return "—" if pd.isna(x) else (f"{x:+.{n}f}" if signed else f"{x:.{n}f}")

def _formation(value:object)->str:
    x=str(value);return "—" if x in {"nan","<NA>","None"} else "-".join(x) if x.isdigit() else x

def _metrics(ui:Any,items:list[tuple[str,str,str|None]])->None:
    for col,(label,value,help_text) in zip(ui.columns(len(items)),items):col.metric(label,value,help=help_text)

def _profile_figure(frame:pd.DataFrame)->go.Figure:
    d=frame.dropna(subset=["Volume Percentile"]);fig=go.Figure(go.Bar(x=d["Volume Percentile"],y=d.Metric,orientation="h",marker_color="#28785a",customdata=d[["Value","League Average","Volume Rank"]],hovertemplate="%{y}<br>Volume percentile %{x:.0f}<br>Team %{customdata[0]:.2f}<br>League %{customdata[1]:.2f}<br>Volume rank %{customdata[2]:.0f}<extra></extra>"));fig.update_xaxes(range=[0,100],title="Volume percentile");fig.update_layout(height=285,margin=dict(l=5,r=5,t=15,b=15),paper_bgcolor="rgba(0,0,0,0)");return fig

def _trend(rows:pd.DataFrame)->go.Figure:
    fig=go.Figure()
    for label,field,color in (("Goals","team_goals","#28785a"),("xG","xg","#3984b6"),("xGA","xga","#c56b55")):
        if field in rows:fig.add_scatter(x=rows.match_date,y=rows[field],mode="lines+markers",name=label,line={"color":color})
    fig.update_layout(height=285,margin=dict(l=5,r=5,t=15,b=10),hovermode="x unified");return fig

def _match_table(rows:pd.DataFrame)->pd.DataFrame:
    d=rows.copy();d["Score"]=d.apply(lambda r:f"{int(r.team_goals)}-{int(r.opponent_goals)}" if pd.notna(r.team_goals) and pd.notna(r.opponent_goals) else "—",axis=1)
    names={"period":"GW","match_date":"Date","home_away":"H/A","opponent_name":"Opponent","result":"Result","xg":"xG","xga":"xGA","formation":"Formation","manager_name":"Manager","shots":"Shots","shots_on_target":"SOT","key_passes":"KP","crosses":"Crosses","take_ons":"TakeOns","successful_tackles":"TkW","interceptions":"Int","aerial_wins":"Aerial Wins","fantasy_points_allowed":"Opponent FPts"}
    return d.rename(columns=names).reindex(columns=["GW","Date","H/A","Opponent","Result","Score","xG","xGA","Formation","Manager","Shots","SOT","KP","Crosses","TakeOns","TkW","Int","Aerial Wins","Opponent FPts"])

def _header(ui:Any,name:str,s:pd.Series,m:pd.Series,f:pd.Series)->None:
    n=int(s.get("matches",0));section_header(ui,name,f"Current sample: {n} match{'es' if n!=1 else ''} observed")
    _metrics(ui,[("Record",str(s.get("record","—")),None),("Manager",str(m.get("manager_name","—")),"Match-observed manager"),("Primary Formation",_formation(f.get("formation","—")),"Observed starting shape"),("Formation Share",_fmt(100*pd.to_numeric(f.get("formation_share"),errors="coerce"),0)+"%","Observed share"),("Played",str(n),"Completed matches")])

def _fingerprint(ui:Any,current:pd.DataFrame,historical:pd.DataFrame,*,key:str)->None:
    method=load_methodology(DEFAULT_METHODOLOGY_PATH);frames=[]
    if not current.empty:frames.append(fingerprint_records(current.iloc[0],method,CURRENT))
    if not historical.empty:frames.append(fingerprint_records(historical.iloc[0],method,"2025/26 Reference"))
    section_header(ui,"Tactical Fingerprint","Transparent percentiles and traits; style describes behavior, not quality.")
    if not frames:ui.info("Tactical fingerprint is unavailable for this club.");return
    shown=pd.concat(frames,ignore_index=True);ui.caption(f"Methodology: {method['methodology_version']} · Current labels require at least 5 matches. Below that threshold, values are observations only.")
    figure=go.Figure()
    for season,group in shown.groupby("Season",sort=False):figure.add_bar(name=season,x=group.Percentile,y=group.Dimension,orientation="h",opacity=1 if season==CURRENT else .45)
    figure.update_xaxes(range=[0,100],title="League percentile");figure.update_layout(barmode="group",height=430,margin=dict(l=5,r=5,t=15,b=15),legend={"orientation":"h"});ui.plotly_chart(figure,use_container_width=True,key=key)
    ui.dataframe(shown[["Season","Dimension","Trait","Percentile","Underlying Metric","Value","Confidence","Why","Caveat"]],hide_index=True,use_container_width=True)
    if not current.empty and int(current.iloc[0].get("matches",0))<5:ui.caption("Current vs 2025/26 observation — the current sample is too small for strong style-change language.")

def _overview(ui:Any,club_id:str,model:dict,history:dict,manager:pd.Series,formation:pd.Series,formation_rows:pd.DataFrame,pieces:pd.DataFrame,tactical:pd.DataFrame,historical_tactical:pd.DataFrame)->None:
    compare=ui.toggle("Compare to 2025/26",value=False,key="team_overview_compare");s=model["summary"]
    _metrics(ui,[("Record",str(s.get("record","—")),None),("Goals",_fmt(s.get("goals_for"),0),None),("xG",_fmt(s.get("xg"),2),"Understat authority"),("xGA",_fmt(s.get("xga"),2),"Understat authority"),("xG Difference",_fmt(s.get("xg_diff"),2,True),None),("Opponent FPts Observed",_fmt(s.get("opponent_fpts_observed"),1),"Official Fantrax observations")])
    matches=int(s.get("matches",0))
    ui.caption(f"Current sample: {matches} match{'es' if matches != 1 else ''} observed · percentiles use all 20 current clubs and are neutral volume percentiles (higher means more, not better).")
    _fingerprint(ui,tactical,historical_tactical,key=f"overview_fingerprint_{club_id}")
    if compare:
        if not history["available"]:ui.info("No 2025/26 Premier League comparison available")
        else:
            h=history["summary"];ui.caption(f"2025/26 comparison: {int(h.get('matches',0))} matches · compatibility-gated cached observations.")
            comparison=pd.DataFrame([{"Metric":"Record","2026/27":s.get("record"),"2025/26":f"{int(h.get('wins',0))}-{int(h.get('draws',0))}-{int(h.get('losses',0))}"},{"Metric":"Goals","2026/27":_fmt(s.get("goals_for"),0),"2025/26":_fmt(h.get("goals_for"),0)},{"Metric":"xG","2026/27":_fmt(s.get("xg"),2),"2025/26":_fmt(h.get("xg"),2)},{"Metric":"xGA","2026/27":_fmt(s.get("xga"),2),"2025/26":_fmt(h.get("xga"),2)},{"Metric":"KP / Match","2026/27":_fmt(s.get("key_passes_per_match"),1),"2025/26":_fmt(h.get("key_passes_per_match"),1)},{"Metric":"Shots / Match","2026/27":_fmt(s.get("shots_per_match"),1),"2025/26":_fmt(h.get("shots_per_match"),1)},{"Metric":"Crosses / Match","2026/27":_fmt(s.get("crosses_per_match"),1),"2025/26":_fmt(h.get("crosses_per_match"),1)},{"Metric":"TakeOns / Match","2026/27":_fmt(s.get("take_ons_per_match"),1),"2025/26":_fmt(h.get("take_ons_per_match"),1)}]);ui.dataframe(comparison,hide_index=True,use_container_width=True)
            for title,panel in history.get("profiles",{}).items():ui.markdown(f"**2025/26 {title}**");ui.dataframe(panel,hide_index=True,use_container_width=True)
    for title,panel in model["profiles"].items():section_header(ui,title,"Team value, league average, neutral volume percentile, and volume rank.");ui.plotly_chart(_profile_figure(panel),use_container_width=True,key=f"team_profile_{club_id}_{title}")
    left,right=ui.columns(2)
    with left:section_header(ui,"Recent Match Trend","Chronological observations; no future zero rows.");ui.plotly_chart(_trend(model["matches"]),use_container_width=True,key=f"team_trend_{club_id}")
    with right:
        section_header(ui,"Next 5 Fixtures","Canonical schedule and existing FDR only.");d=model["fixtures"].rename(columns={"opponent":"Opponent","home_away":"H/A","date":"Date","fantrax_period":"GW","fixture_difficulty":"FDR"});ui.dataframe(d.reindex(columns=["GW","Date","H/A","Opponent","FDR"]),hide_index=True,use_container_width=True)
    section_header(ui,"Manager + Formation","Observed context; not a prediction.");_metrics(ui,[("Manager",str(manager.get("manager_name","—")),None),("Primary Formation",_formation(formation.get("formation","—")),None),("Formation Share",_fmt(100*pd.to_numeric(formation.get("formation_share"),errors="coerce"),0)+"%",None),("Observed Matches",str(int(formation.get("matches",0))),None)])
    if not formation_rows.empty:
        d=formation_rows.rename(columns={"formation":"Formation","matches":"Matches","formation_share":"Share"});d["Formation"]=d.Formation.map(_formation);ui.dataframe(d[["Formation","Matches","Share"]],hide_index=True,use_container_width=True)
    section_header(ui,"Set Pieces","Observed taker hierarchy; no left/right corner claims.")
    if pieces.empty:ui.info("No validated set-piece attempts in this sample.")
    else:ui.dataframe(pieces.rename(columns={"set_piece_type":"Type","rank":"Rank","player_name":"Taker","attempts":"Attempts","player_share":"Share","sample_size":"Sample"})[["Type","Rank","Taker","Attempts","Share","Sample"]],hide_index=True,use_container_width=True)

def _match_analysis(ui:Any,current:pd.DataFrame,history:pd.DataFrame,club_id:str,fantasy:pd.DataFrame,current_context:pd.DataFrame,historical_context:pd.DataFrame)->None:
    season=ui.radio("Season",[CURRENT,HISTORICAL],horizontal=True,key="team_match_season");venue=ui.radio("Home / Away",["All","Home","Away"],horizontal=True,key="team_match_venue");base=current if season==CURRENT else history;cid=club_id if season==CURRENT or base.empty else str(base.club_id.iloc[0]);model=prepare_team_match_analysis(base,cid,venue=venue);rows=model["rows"].copy();s=model["summary"]
    if season==CURRENT and not rows.empty and not fantasy.empty:rows=rows.merge(fantasy[["canonical_match_id","fantasy_points_allowed"]],on="canonical_match_id",how="left")
    if rows.empty:ui.info("No matches are available for this season and scope.");return
    _metrics(ui,[("Matches",str(int(s.get("matches",0))),None),("W-D-L",f"{int(s.get('wins',0))}-{int(s.get('draws',0))}-{int(s.get('losses',0))}",None),("Goals",_fmt(s.get("goals_for"),0),None),("xG",_fmt(s.get("xg"),2),"— when unsupported"),("xGA",_fmt(s.get("xga"),2),"— when unsupported"),("xG Diff",_fmt(s.get("xg_diff"),2,True),None)]);section_header(ui,"Chronological Match Log","Canonical results and compact observed components.");ui.dataframe(_match_table(rows),hide_index=True,use_container_width=True)
    fig=go.Figure();fig.add_scatter(x=rows.match_date,y=rows.xg,name="xG",mode="lines+markers");fig.add_scatter(x=rows.match_date,y=rows.xga,name="xGA",mode="lines+markers");fig.update_layout(height=300,margin=dict(l=5,r=5,t=20,b=10),hovermode="x unified");ui.plotly_chart(fig,use_container_width=True,key=f"team_match_xg_{season}_{venue}")
    context=current_context if season==CURRENT else historical_context
    context=context[context.get("canonical_match_id",pd.Series(index=context.index,dtype=object)).astype(str).isin(rows.canonical_match_id.astype(str))]
    if not context.empty:
        trait_columns=[c for c in context if c.startswith("opponent_") and c.endswith("_trait")]
        compact=context[["canonical_match_id","opponent_id",*trait_columns]].copy();compact["Opponent Traits"]=compact[trait_columns].apply(lambda r:" · ".join(x for x in r.astype(str) if x not in {"—","Observation only","nan"}),axis=1)
        with ui.expander("Opponent tactical context"):ui.dataframe(compact[["canonical_match_id","opponent_id","Opponent Traits"]],hide_index=True,use_container_width=True)

def _tactical(ui:Any,current:pd.DataFrame,history:pd.DataFrame,events:pd.DataFrame,club_id:str,managers:pd.DataFrame,formations:pd.DataFrame,venues:pd.DataFrame,data:DataManager,hmanagers:pd.DataFrame,hformations:pd.DataFrame,hvenues:pd.DataFrame,tactical:pd.DataFrame,historical_tactical:pd.DataFrame)->None:
    _fingerprint(ui,tactical,historical_tactical,key=f"tactical_fingerprint_{club_id}")
    season=ui.radio("Season",[CURRENT,HISTORICAL],horizontal=True,key="team_tactical_season");base=current if season==CURRENT else history;cid=club_id if season==CURRENT or base.empty else str(base.club_id.iloc[0])
    if base.empty:ui.info("No 2025/26 Premier League comparison available");return
    if season==HISTORICAL:events=_load(data,"player_pitch_events","2526",True);managers=hmanagers;formations=hformations;venues=hvenues
    scope=ui.selectbox("Scope",["Season","Last 10","Last 5","Individual Match"],key="team_tactical_scope");venue=ui.selectbox("Home / Away",["All","Home","Away"],key="team_tactical_venue");formation=ui.selectbox("Formation",["All",*sorted(base.formation.dropna().astype(str).unique())],format_func=lambda x:"All" if x=="All" else _formation(x),key="team_tactical_formation");manager=ui.selectbox("Manager",["All",*sorted(base.manager_name.dropna().astype(str).unique())],key="team_tactical_manager");match_id=None
    if scope=="Individual Match":labels={f"{r.match_date} · {r.opponent_id} ({r.home_away})":r.canonical_match_id for r in base.itertuples()};chosen=ui.selectbox("Individual Match",list(labels),key="team_tactical_match");match_id=labels.get(chosen)
    filters=dict(scope=scope,venue=venue,formation=formation,manager=manager,match_id=match_id);model=prepare_team_tactical_profile(base,events,cid,**filters);selected=model["matches"];s=model["summary"];ui.caption(f"{len(selected)} match{'es' if len(selected)!=1 else ''} observed · Event Activity is recorded data, not touches, tracking, possession territory, or average position.")
    _metrics(ui,[("Final-Third Entries",_fmt(s.get("final_third_entries_per_match"),1),"Successful passes entering from outside"),("Box Entries",_fmt(s.get("box_entries_per_match"),1),"Successful passes entering from outside"),("Cross Attempts",_fmt(s.get("crosses_per_match"),1),None),("Successful Crosses",_fmt(s.get("successful_crosses_per_match"),1),None),("TakeOn Attempts",_fmt(s.get("take_ons_per_match"),1),None),("Successful TakeOns",_fmt(s.get("successful_take_ons_per_match"),1),None)])
    layer=ui.selectbox("Event Activity Layer",list(EVENT_LAYERS),key="team_event_layer");activity=prepare_team_events(events,selected,cid,layer);section_header(ui,"Team Event Activity","Opponent goal is at the top; raw provider coordinates remain unchanged.")
    if activity.empty:ui.info("Compatible compact event-location evidence is unavailable; no pitch map is fabricated.")
    else:
        fig=draw_pitch(height=560);add_points(fig,activity,colors=pd.Series("#28785a",index=activity.index),size=6);ui.plotly_chart(fig,use_container_width=True,key=f"team_pitch_{season}_{scope}_{venue}_{formation}_{manager}_{layer}");z=model["zones"];section_header(ui,"Event Activity by Zone","Descriptive share of recorded actions.");_metrics(ui,[("Defensive Third",_fmt(z.get("defensive_third_share"),1)+"%",None),("Middle Third",_fmt(z.get("middle_third_share"),1)+"%",None),("Final Third",_fmt(z.get("final_third_share"),1)+"%",None),("Left",_fmt(z.get("left_share"),1)+"%",None),("Center",_fmt(z.get("center_share"),1)+"%",None),("Right",_fmt(z.get("right_share"),1)+"%",None)])
    section_header(ui,"Observed Splits","Manager, formation, and venue differences are descriptive, not causal.")
    for label,frame in (("Manager Regimes",managers),("Formation Splits",formations),("Home / Away Splits",venues)):ui.markdown(f"**{label}**");ui.dataframe(frame.drop(columns=["club_id","club_name","feature_class","contains_prediction"],errors="ignore"),hide_index=True,use_container_width=True)

def _fantasy(ui:Any,total:pd.DataFrame,position:pd.DataFrame,club_id:str,history:pd.DataFrame)->None:
    season=ui.radio("Season",[CURRENT,HISTORICAL],horizontal=True,key="team_fantasy_season")
    if season==HISTORICAL:
        if history.empty:ui.info("No 2025/26 Premier League fantasy reference available")
        else:
            ui.caption("2025/26 historical reference · exact single-primary-position Fantrax attribution; validated historical ease ranks are retained only in detail.")
            names={"position_group":"Position","matches":"Matches","points_allowed":"FPts","points_allowed_per_match":"FPts / Match","ghost_allowed":"Ghost","ghost_allowed_per_match":"Ghost / Match","goals_allowed":"G","assists_allowed":"A","key_passes_allowed":"KP","shots_on_target_allowed":"SOT","accurate_crosses_allowed":"AC","tackles_won_allowed":"TkW","interceptions_allowed":"Int","clearances_allowed":"CLR","aerial_wins_allowed":"AER"};ui.dataframe(history.rename(columns=names).reindex(columns=list(names.values())),hide_index=True,use_container_width=True)
            with ui.expander("Validated historical rank detail"):ui.dataframe(history,hide_index=True,use_container_width=True)
        return
    model=prepare_team_fantasy_matchups(total,position,club_id);s=model["summary"];rows=model["positions"];ui.caption(f"Current observed sample: {model['matches']} match · observational only; no rankings, grades, or projections.");_metrics(ui,[("Matches",str(model["matches"]),None),("Opponent FPts",_fmt(s.get("fantasy_points_allowed"),1),"Official Fantrax"),("Opponent Ghost",_fmt(s.get("ghost_allowed"),1),"Established Ghost methodology"),("Goals Allowed",_fmt(s.get("goals_allowed"),0),None),("Assists Allowed",_fmt(s.get("assists_allowed"),0),None),("KP Allowed",_fmt(s.get("key_passes_allowed"),0),None)])
    rename={"position_group":"Position","matches_observed":"Matches","fantasy_points_allowed":"FPts","fpts_per_match":"FPts / Match","ghost_allowed":"Ghost","ghost_per_match":"Ghost / Match","goals_allowed":"G","assists_allowed":"A","key_passes_allowed":"KP","accurate_crosses_allowed":"AC","tackles_won_allowed":"TkW","interceptions_allowed":"Int","clearances_allowed":"CLR","aerial_wins_allowed":"AER"};ui.dataframe(rows.rename(columns=rename),hide_index=True,use_container_width=True)
    with ui.expander("Fantasy Matchups methodology"):ui.markdown("FPts uses official Fantrax match-attributable observations. Ghost uses the established Ghost methodology. Detailed components use Fantrax when observed; validated provider supplements may fill missing detail. Waiver detail is not fabricated. An em dash means unavailable or no positional sample; zero means an observed zero. Current data is a small sample.")

def render(season_id:str,ui:Any=st,data_manager:DataManager|None=None)->None:
    data=data_manager or DataManager();clubs=_load(data,"premier_league_clubs",season_id);matches=_load(data,"team_match_analytics",season_id);profiles=_load(data,"team_season_profile",season_id);managers=_load(data,"team_manager_profile",season_id);formations=_load(data,"team_formation_analytics",season_id);venues=_load(data,"team_home_away_profile",season_id);fantasy=_load(data,"team_fantasy_allowed_match",season_id);position=_load(data,"team_fantasy_allowed_position_match",season_id);fixtures=_load(data,"team_fixtures",season_id);events=_load(data,"whoscored_event",season_id,True);historical=_load(data,"team_match_analytics","2526",True);hprofiles=_load(data,"team_season_profile","2526",True);hmanagers_all=_load(data,"team_manager_profile","2526",True);hformations_all=_load(data,"team_formation_analytics","2526",True);hvenues_all=_load(data,"team_home_away_profile","2526",True);historical_allowed_all=_load(data,"historical_fantasy_allowed_ranked",season_id,True);tactical_all=_load(data,"team_tactical_profile",season_id,True);historical_tactical_all=_load(data,"team_tactical_profile","2526",True);context_all=_load(data,"team_opponent_tactical_context",season_id,True);historical_context_all=_load(data,"team_opponent_tactical_context","2526",True)
    page_header(ui,"Teams","Team Directory · current-first performance, match, tactical activity, and descriptive fantasy research",badge=CURRENT)
    if clubs.empty or matches.empty:ui.info("Canonical current team analytics are unavailable.");return
    names=clubs[["canonical_name","canonical_club_id"]].drop_duplicates().sort_values("canonical_name");selected=ui.selectbox("Club",names.canonical_name.tolist(),key="team_selector");club_id=str(names.loc[names.canonical_name.eq(selected),"canonical_club_id"].iloc[0]);hid=historical_club_id(club_id);overview=prepare_team_overview(club_id,matches,profiles,fantasy,fixtures);history=prepare_team_historical_comparison(club_id,historical);history["profiles"]=prepare_team_profile_percentiles(hprofiles,hid) if history["available"] else {};manager_rows=managers[managers.club_id.astype(str).eq(club_id)].sort_values("matches",ascending=False);formation_rows=formations[formations.club_id.astype(str).eq(club_id)].sort_values("matches",ascending=False);venue_rows=venues[venues.club_id.astype(str).eq(club_id)];hmanager_rows=hmanagers_all[hmanagers_all.club_id.astype(str).eq(hid)].sort_values("matches",ascending=False);hformation_rows=hformations_all[hformations_all.club_id.astype(str).eq(hid)].sort_values("matches",ascending=False);hvenue_rows=hvenues_all[hvenues_all.club_id.astype(str).eq(hid)];historical_allowed=historical_allowed_all[historical_allowed_all.get("opponent_id",pd.Series(index=historical_allowed_all.index,dtype=object)).astype(str).eq(hid)];tactical=tactical_all[tactical_all.club_id.astype(str).eq(club_id)];historical_tactical=historical_tactical_all[historical_tactical_all.club_id.astype(str).eq(hid)] if history["available"] else historical_tactical_all.iloc[0:0];manager=manager_rows.iloc[0] if not manager_rows.empty else pd.Series(dtype=object);formation=formation_rows.iloc[0] if not formation_rows.empty else pd.Series(dtype=object);_header(ui,selected,overview["summary"],manager,formation);tabs=ui.tabs(list(TABS));current_bundle=get_historical_team_advanced(data,club_id,season=season_id,ui=ui);pieces=current_bundle.set_pieces
    if not pieces.empty:pieces=pieces[pieces.window.eq("SEASON")&pieces["rank"].le(3)]
    with tabs[0]:_overview(ui,club_id,overview,history,manager,formation,formation_rows,pieces,tactical,historical_tactical)
    with tabs[1]:_match_analysis(ui,matches,history["matches"],club_id,fantasy[fantasy.club_id.astype(str).eq(club_id)],context_all[context_all.club_id.astype(str).eq(club_id)],historical_context_all[historical_context_all.club_id.astype(str).eq(hid)])
    with tabs[2]:_tactical(ui,matches,history["matches"],events,club_id,manager_rows,formation_rows,venue_rows,data,hmanager_rows,hformation_rows,hvenue_rows,tactical,historical_tactical)
    with tabs[3]:_fantasy(ui,fantasy,position,club_id,historical_allowed)
