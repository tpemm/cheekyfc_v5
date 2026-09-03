#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fantrax.live.whoscored_semantics import observed_event_counts,safe_fantasy_assist_delta
from integrations.whoscored.workflows import atomic_csv,atomic_json

def metrics(frame,f,w,label):
    a=pd.to_numeric(frame[f],errors="coerce");b=pd.to_numeric(frame[w],errors="coerce");ok=a.notna()&b.notna();d=b[ok]-a[ok]
    return {"metric":label,"fantrax_field":f,"whoscored_field":w,"sample_size":int(ok.sum()),"exact_agreement":float(d.eq(0).mean()) if len(d) else None,"mae":float(d.abs().mean()) if len(d) else None,"fantrax_total":float(a[ok].sum()),"derived_total":float(b[ok].sum()),"mismatches":int(d.ne(0).sum())}

def main(season="2627",period=1):
    t=time.perf_counter();m=ROOT/f"data/models/season_{season}";q=ROOT/f"data/quality/season_{season}";adv=m/"advanced"
    fan=pd.read_csv(m/f"current_player_weekly_{season}.csv",low_memory=False);fan=fan[fan.current_manager_id.notna()&fan.period.eq(period)].copy();fan.fantrax_player_id=fan.fantrax_player_id.astype(str)
    events=pd.read_csv(adv/f"whoscored_event_{season}.csv",low_memory=False);counts=observed_event_counts(events)
    identity=pd.read_csv(ROOT/"data/reference/whoscored_player_identity.csv",dtype={"fantrax_player_id":str});bridge=identity.dropna(subset=["canonical_player_id","fantrax_player_id"]).drop_duplicates("canonical_player_id").set_index("canonical_player_id").fantrax_player_id
    counts["fantrax_player_id"]=counts.canonical_player_id.astype(str).map(bridge)
    observed=pd.read_csv(adv/f"supplemental_player_match_{season}.csv",low_memory=False);observed=observed[pd.to_numeric(observed.get('fantrax_period'),errors='coerce').eq(period)];observed=observed.dropna(subset=["fantrax_player_id"])[["canonical_match_id","canonical_player_id","fantrax_player_id"]].drop_duplicates();observed.fantrax_player_id=observed.fantrax_player_id.astype(str)
    counts=observed.merge(counts.drop(columns=["fantrax_player_id"],errors="ignore"),on=["canonical_match_id","canonical_player_id"],how="left")
    # A lineup/player-match observation establishes observed zero when no event
    # of a derived type exists. Players without that observation never enter.
    ws_columns=[c for c in counts if c.startswith("ws_")];counts[ws_columns]=counts[ws_columns].fillna(0)
    joined=fan.merge(counts,on="fantrax_player_id",how="inner",suffixes=("_fantrax","_ws"))
    specs=[("accurate_crosses","ws_cross_attempts","cross_attempts"),("accurate_crosses","ws_cross_successful","accurate_crosses"),("shots_on_target","ws_sot_goal_saveds","sot_goal_saved"),("shots_on_target","ws_sot_goal_saved_unblockeds","sot_goal_saved_unblocked"),("shots_on_target","ws_sot_successful_shots","sot_successful_shot"),("tackles_won","ws_tackle_attempts","tackle_attempts"),("tackles_won","ws_tackle_successful","tackles_successful"),("clearances","ws_clearances","clearances"),("goals","ws_goals","goals"),("assists","ws_official_assists","official_assists")]
    summary=pd.DataFrame([metrics(joined,*x) for x in specs]);atomic_csv(summary,q/f"fantrax_whoscored_semantic_validation_gw{period}_{season}.csv")
    per_gw=[]
    for path in sorted(q.glob(f"fantrax_whoscored_semantic_validation_gw*_{season}.csv")):
        part=pd.read_csv(path);part["period"]=int(path.stem.split("gw",1)[1].split("_",1)[0]);per_gw.append(part)
    all_results=pd.concat(per_gw,ignore_index=True) if per_gw else summary.assign(period=period)
    cumulative=[]
    for metric,rows in all_results.groupby("metric"):
        n=int(rows.sample_size.sum());exact=int(round((rows.exact_agreement*rows.sample_size).sum()));cumulative.append({"periods_included":",".join(map(str,sorted(rows.period.unique()))),"matches_included":10*rows.period.nunique(),"metric":metric,"fantrax_field":rows.fantrax_field.iloc[-1],"whoscored_field":rows.whoscored_field.iloc[-1],"sample_size":n,"exact_agreement":exact/n if n else None,"mae":float((rows.mae*rows.sample_size).sum()/n) if n else None,"fantrax_total":rows.fantrax_total.sum(),"derived_total":rows.derived_total.sum(),"mismatches":int(rows.mismatches.sum())})
    atomic_csv(pd.DataFrame(cumulative),q/f"fantrax_whoscored_semantic_validation_cumulative_{season}.csv")
    definitions={"cross":("accurate_crosses","ws_cross_attempts","ws_cross_successful"),"sot":("shots_on_target","ws_sot_goal_saveds","ws_sot_goal_saved_unblockeds","ws_sot_successful_shots"),"tackle":("tackles_won","ws_tackle_attempts","ws_tackle_successful")}
    for name,cols in definitions.items():
        detail=joined[["fantrax_player_id","player_name","club","canonical_match_id",*cols]].copy();atomic_csv(detail,q/f"fantrax_{name}_validation_gw{period}_{season}.csv")
    clear=joined[pd.to_numeric(joined.clearances,errors="coerce").ne(pd.to_numeric(joined.ws_clearances,errors="coerce"))][["fantrax_player_id","player_name","club","canonical_match_id","minutes","start","clearances","ws_clearances"]].copy();clear["explanation"]="PROVIDER_DEFINITION_OR_STAT_CORRECTION";atomic_csv(clear,q/f"fantrax_clearance_mismatches_gw{period}_{season}.csv")
    under=pd.read_csv(m/f"understat_player_match_{season}.csv",low_memory=False);under.fantrax_player_id=under.fantrax_player_id.astype(str);assists=joined.merge(under[["fantrax_player_id","assists"]].rename(columns={"assists":"understat_official_assists"}),on="fantrax_player_id",how="left");assists["fantasy_assist_delta"]=safe_fantasy_assist_delta(assists.assists,assists.ws_official_assists);atomic_csv(assists[["fantrax_player_id","player_name","club","canonical_match_id","assists","ws_official_assists","understat_official_assists","fantasy_assist_delta"]],q/f"fantrax_assist_validation_gw{period}_{season}.csv")
    fantasy=assists[assists.fantasy_assist_delta.gt(0)].copy();diagnostics=[]
    for row in fantasy.itertuples():
        match=events[events.canonical_match_id.eq(row.canonical_match_id)].sort_values(["expanded_minute","second","provider_sequence_event_id"]);goals=match[match.event_type.eq("Goal")]
        actor=match[match.canonical_player_id.astype(str).eq(str(row.canonical_player_id))]
        best=None
        for _,goal in goals.iterrows():
            before=actor[(pd.to_numeric(actor.expanded_minute,errors="coerce")<goal.expanded_minute)|((pd.to_numeric(actor.expanded_minute,errors="coerce")==goal.expanded_minute)&(pd.to_numeric(actor.second,errors="coerce")<=goal.second))].tail(1)
            if len(before):best=(goal,before.iloc[0])
        goal,prev=best if best else (pd.Series(dtype=object),pd.Series(dtype=object));ptype=prev.get("event_type",pd.NA);pqual=prev.get("qualifiers",pd.NA)
        category="SAVED_SHOT_REBOUND" if ptype=="SavedShot" else "BLOCKED_SHOT" if isinstance(pqual,str) and '"Blocked"' in pqual else "OTHER" if pd.notna(ptype) else "UNRESOLVED"
        diagnostics.append({"fantrax_player_id":row.fantrax_player_id,"player_name":row.player_name,"club":row.club,"canonical_match_id":row.canonical_match_id,"fantrax_assists":row.assists,"ws_official_assists":row.ws_official_assists,"understat_official_assists":row.understat_official_assists,"fantasy_assist_delta":row.fantasy_assist_delta,"goal_event_id":goal.get("event_id",pd.NA),"goal_scorer_id":goal.get("canonical_player_id",pd.NA),"goal_minute":goal.get("expanded_minute",pd.NA),"previous_event_id":prev.get("event_id",pd.NA),"previous_event_type":ptype,"previous_event_outcome":prev.get("outcome",pd.NA),"previous_event_qualifiers":pqual,"event_category":category,"candidate_rule":"REVIEW_ONLY_NOT_PRODUCTION"})
    atomic_csv(pd.DataFrame(diagnostics),q/f"fantrax_fantasy_assist_event_audit_gw{period}_{season}.csv")
    classifications=pd.DataFrame([("Goals","SAFE_SUPPLEMENT"),("Fantasy Assists","SOURCE_SPECIFIC"),("Official Assists","SOURCE_SPECIFIC"),("Key Passes","SAFE_SUPPLEMENT"),("Shots on Target","NEEDS_MORE_SAMPLE"),("Tackles Won","SAFE_SUPPLEMENT"),("Interceptions","SAFE_SUPPLEMENT"),("Clearances","CAVEAT_SUPPLEMENT"),("Aerial Wins","SAFE_SUPPLEMENT"),("Accurate Crosses","SAFE_SUPPLEMENT")],columns=["metric","classification"]);atomic_csv(classifications,q/f"fantrax_whoscored_semantic_classification_gw{period}_{season}.csv")
    unified=pd.read_csv(m/f"live_player_weekly_enriched_{season}.csv",low_memory=False);w=unified[unified.fantrax_detail_source.eq("FANTRAX_ALL_PLAYER_ONLY")];approved=set(classifications[classifications.classification.eq("SAFE_SUPPLEMENT")].metric);coverage=pd.DataFrame([{"metric":x,"waiver_players":len(w),"whoscored_observed":int(w.whoscored_available.sum()),"understat_observed":int(w.understat_available.sum()),"approved":x in approved,"would_receive_validated_value":int(w.whoscored_available.sum()) if x in approved else 0} for x in classifications.metric]);atomic_csv(coverage,q/f"waiver_supplement_coverage_gw{period}_{season}.csv")
    correction_columns=["provider","period","match","canonical_player_id","player","club","field","old_value","new_value","difference","old_snapshot","new_snapshot","active_starter","manager_affected","downstream_impact"]
    fan_diff_path=q/f"fantrax_gw{period}_corrections_{season}.csv";fan_diff=pd.read_csv(fan_diff_path) if fan_diff_path.exists() else pd.DataFrame();corrections=[]
    for row in fan_diff.itertuples():corrections.append({"provider":"Fantrax","period":period,"canonical_player_id":getattr(row,"canonical_player_id",pd.NA),"player":getattr(row,"player_name",pd.NA),"field":row.metric,"old_value":row.old_value,"new_value":row.new_value,"difference":row.delta,"old_snapshot":row.previous_snapshot,"new_snapshot":row.new_snapshot,"manager_affected":getattr(row,"manager_id",pd.NA),"downstream_impact":"full source rebuild"})
    atomic_csv(pd.DataFrame(corrections,columns=correction_columns),q/f"provider_corrections_gw{period}_{season}.csv")
    report={"exact_observations":len(joined),"players":int(joined.fantrax_player_id.nunique()),"clubs":int(joined.club.nunique()),"matches":int(joined.canonical_match_id.nunique()),"periods_included":[period],"started":int(pd.to_numeric(joined.start,errors="coerce").fillna(0).gt(0).sum()),"substitutes":int(pd.to_numeric(joined.start,errors="coerce").fillna(0).eq(0).sum()),"fantasy_assist_only":len(fantasy),"clearance_mismatches":len(clear),"provider_corrections":len(corrections),"elapsed_seconds":round(time.perf_counter()-t,3)};atomic_json(report,q/f"semantic_validation_summary_gw{period}_{season}.json");print(json.dumps(report,indent=2));return 0
if __name__=="__main__":p=argparse.ArgumentParser();p.add_argument("--season",default="2627");p.add_argument("--period",type=int,default=1);a=p.parse_args();raise SystemExit(main(a.season,a.period))
