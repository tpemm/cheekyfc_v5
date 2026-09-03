"""Compact, transparent Player Overview presentation preparation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.players.comparison import primary_position, stable_player_id
from analytics.players.ranking import metric_ranking

DEFAULT_RADAR_KEYS=("ghost_start","points_start","season_points","games_started")
OVERVIEW_METRICS={
    "ghost_start":("Ghost / Start","current_ghost_per_start","historical_ghost_per_start","Ghost floor"),
    "points_start":("Points / Start","current_points_per_start","historical_points_per_start","Fantasy production"),
    "season_points":("Season Points","current_fantasy_points","historical_fantasy_points","Fantasy production"),
    "games_started":("Games Started","current_starts","historical_starts","Playing time"),
    "xgi_90":("xGI / 90","current_xgi_per_90","historical_xgi_per_90","Attacking output"),
    "start_pct":("Start %","current_start_percentage","historical_start_percentage","Playing time"),
    "minutes":("Minutes","current_minutes","historical_minutes","Playing time"),
    "minutes_outlook":("Minutes Outlook","projected_minutes_percentage",None,"Current projection"),
    "fixture_ease":("Next 5 Fixture Ease","next_five_fixture_ease_percentile",None,"Current fixture model"),
}
EXACT_STATS=("points_start","ghost_start","season_points","games_started","xgi_90","minutes_outlook")


def qualitative_label(percentile)->str:
    value=pd.to_numeric(percentile,errors="coerce")
    if pd.isna(value): return "Unavailable"
    if value>=90:return "Elite"
    if value>=75:return "Strong"
    if value>=40:return "League Average"
    if value>=20:return "Below Average"
    return "Weak"


def overview_radar_records(frame:pd.DataFrame,row:pd.Series,keys:tuple[str,...],peer_basis:str)->list[dict]:
    records=[]
    for season,index in (("2026/27 Current",1),("2025/26 Historical",2)):
        metrics=[]
        for key in keys:
            if key not in OVERVIEW_METRICS: continue
            label,current,historical,source=OVERVIEW_METRICS[key]; field=(current,historical)[index-1]
            prepared=(pd.DataFrame({"value":np.nan,"percentile":np.nan,"rank":np.nan,"peer_count":0},index=frame.index) if field is None else metric_ranking(frame,field,peer_basis=peer_basis))
            ranked=prepared.loc[row.name]; raw=ranked["value"]; peer_count=int(ranked["peer_count"])
            metrics.append({"key":key,"label":label,"raw":raw,"formatted":"\u2014" if pd.isna(raw) else f"{raw:,.1f}","percentile":ranked["percentile"],"rank":ranked["rank"],"peer_count":peer_count,"peer_group":peer_basis,"source":source,"low_peers":peer_basis=="Position" and peer_count<5})
        records.append({"player_id":stable_player_id(row),"player_name":season,"metrics":metrics})
    return records


def valid_radar_records(records:list[dict],mode:str)->list[dict]:
    selected=records[:1] if mode=="Current Season" else records[1:] if mode=="2025/26 Historical" else records
    if not selected:return selected
    valid={metric["key"] for metric in selected[0]["metrics"] if pd.notna(metric["percentile"])}
    for record in selected[1:]: valid&={metric["key"] for metric in record["metrics"] if pd.notna(metric["percentile"])}
    return [{**record,"metrics":[metric for metric in record["metrics"] if metric["key"] in valid]} for record in selected]


def exact_stats_frame(row:pd.Series,mode:str)->pd.DataFrame:
    rows=[]
    for key in EXACT_STATS:
        label,current,historical,_=OVERVIEW_METRICS[key]
        item={"Stat":label}
        if mode in ("Current Season","Overlay Both"): item["2026/27"]=row.get(current)
        if mode in ("2025/26 Historical","Overlay Both"): item["2025/26"]=row.get(historical) if historical else pd.NA
        rows.append(item)
    return pd.DataFrame(rows)


def _peer_values(frame,row,field,basis):
    values=pd.to_numeric(frame.get(field,pd.Series(np.nan,index=frame.index)),errors="coerce")
    if basis=="Position": values=values[frame.apply(primary_position,axis=1).eq(primary_position(row))]
    return values


def _bar(label,basis,raw,values):
    raw=pd.to_numeric(raw,errors="coerce"); pct=np.nan
    if pd.notna(raw):
        count=int(values.count()); pct=float(values.le(raw).sum()/count*100) if count else np.nan; rank=int((values>raw).sum()+1) if count else 0
    else: rank=count=0
    return {"label":label,"basis":basis,"raw":raw,"percentile":pct,"rank":rank,"peer_count":count,"qualitative":qualitative_label(pct)}


def overview_bars(frame:pd.DataFrame,row:pd.Series,mode:str,peer_basis:str,current_weekly:pd.DataFrame,historical_weekly:pd.DataFrame)->list[dict]:
    historical=mode=="2025/26 Historical"; suffix="historical" if historical else "current"
    specs=[("Fantasy Production","Points / Start",f"{suffix}_points_per_start"),
           ("Points Floor","Ghost / Start",f"{suffix}_ghost_per_start")]
    bars=[]
    for label,basis,field in specs: bars.append(_bar(label,basis,row.get(field),_peer_values(frame,row,field,peer_basis)))
    weekly=historical_weekly if historical else current_weekly; id_field="historical_fantrax_player_id" if historical else "fantrax_player_id"; selected_id=str(row.get(id_field,""))
    complete=weekly.copy()
    if not historical and not complete.empty: complete=complete[complete.get("period_complete",pd.Series(False,index=complete.index)).fillna(False).astype(bool)]
    if not complete.empty:
        ids=complete.get("fantrax_player_id",pd.Series(index=complete.index,dtype=object)).astype(str).str.strip("*")
        scores=pd.to_numeric(complete.get("fantasy_points",complete.get("mgr_fantasy_points")),errors="coerce")
        if historical and "avail_fpts" in complete: scores=scores.combine_first(pd.to_numeric(complete["avail_fpts"],errors="coerce"))
        maxima=scores.groupby(ids).max(); ceiling=maxima.get(selected_id.strip("*"),np.nan)
        if peer_basis=="Position":
            peers=frame[frame.apply(primary_position,axis=1).eq(primary_position(row))]
            peer_field="historical_fantrax_player_id" if historical else "fantrax_player_id"
            peer_ids=peers.get(peer_field,pd.Series(index=peers.index,dtype=object)).dropna().astype(str).str.strip("*")
            maxima=maxima[maxima.index.isin(set(peer_ids))]
    else: maxima=pd.Series(dtype=float); ceiling=np.nan
    bars.append(_bar("Points Ceiling","Highest completed weekly score",ceiling,maxima))
    if historical: field="historical_start_percentage"; basis="Start %"
    else: field="projected_minutes_percentage"; basis="Minutes Outlook"
    bars.append(_bar("Playing Time",basis,row.get(field),_peer_values(frame,row,field,peer_basis)))
    fixture_field="next_five_fixture_ease_percentile"; bars.append(_bar("Next 5 Fixture Outlook","Current Context \u00b7 Next 5 Fixture Ease",row.get(fixture_field),_peer_values(frame,row,fixture_field,"League")))
    return bars
