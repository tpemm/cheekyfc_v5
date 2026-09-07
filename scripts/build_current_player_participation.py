#!/usr/bin/env python3
"""Build Sprint 9.8A canonical participation, match log, summary, and audits."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from fantrax.live.player_participation import starter_observation_rates, add_canonical_rates, build_player_match_participation, overlay_weekly_participation
from fantrax.live.ghost import derive_return_ghost
from fantrax.analytics.core.fantrax_scoring import effective_rules, get_rule, score_stat
from fantrax.analytics.core.scoring_engine import parse_eligible_positions
from integrations.whoscored.workflows import atomic_csv, atomic_json

def read(path): return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
def numeric(frame, column): return pd.to_numeric(frame.get(column, pd.Series(index=frame.index, dtype=float)), errors="coerce")

SCORING_COLUMNS={"AC":"accurate_crosses","AER":"aerials_won","AT":"assists","BS":"blocks","CS":"clean_sheets","DIS":"dispossessions","CLR":"clearances","G":"goals","Int":"interceptions","KP":"key_passes","OG":"own_goals","PKD":"penalties_drawn","PKM":"penalties_missed","RC":"red_cards","SOT":"shots_on_target","CoS":"successful_dribbles","TkW":"tackles_won","YC":"yellow_cards","GA":"goals_against","PKS":"penalties_saved","Sv":"saves","Sm":"smothers","HCS":"high_claims"}

def build_scoring_validation(weekly, season, quality):
    atomic_csv(pd.DataFrame(effective_rules(season)),quality/f"fantrax_scoring_effective_rules_{season}.csv")
    rows=[]
    for _,row in weekly[pd.to_numeric(weekly.get("fantasy_points"),errors="coerce").notna()].iterrows():
        positions=parse_eligible_positions(row.get("started_position"),row.get("canonical_position") or row.get("fantrax_position"));pos=positions[0] if positions else ""
        available=[];missing=[];total=0.0
        if pos:
            for stat,column in SCORING_COLUMNS.items():
                try: rule=get_rule(season,pos,stat)
                except KeyError: continue
                if rule.get("type")=="flat" and float(rule.get("points_each",0))==0: continue
                value=pd.to_numeric(pd.Series([row.get(column)]),errors="coerce").iloc[0]
                if pd.isna(value): missing.append(stat)
                else: available.append(stat);total+=score_stat(season,pos,stat,value)
        fantrax=float(row["fantasy_points"]);difference=total-fantrax if pos else pd.NA
        status="COMPLETE_EXACT" if pos and not missing and abs(difference)<=.01 else ("COMPLETE_MISMATCH" if pos and not missing else ("POSITION_AMBIGUITY" if not pos else "MISSING_COMPONENT"))
        rows.append({"player":row.get("player_name"),"Fantrax ID":row.get("fantrax_player_id"),"period":row.get("period"),"position used":pos or pd.NA,"Fantrax FPts":fantrax,"reconstructed FPts":total if pos else pd.NA,"difference":difference,"components available":"|".join(available),"components missing":"|".join(missing),"validation status":status})
    validation=pd.DataFrame(rows);atomic_csv(validation,quality/f"fantrax_scoring_config_validation_{season}.csv")
    return validation

def main(season="2627"):
    model=ROOT/f"data/models/season_{season}"; advanced=model/"advanced"; quality=ROOT/f"data/quality/season_{season}"
    lineup=read(advanced/f"whoscored_lineup_{season}.csv"); matches=read(advanced/f"whoscored_match_{season}.csv")
    weekly=read(model/f"current_player_weekly_{season}.csv"); understat=read(model/f"understat_player_match_{season}.csv")
    raw_paths=sorted((ROOT/f"data/raw/fantrax/{season}/player_stats").glob("period_*/weekly_player_stats.csv"));scoring_weekly=weekly
    if raw_paths:
        raw=pd.concat([pd.read_csv(path,low_memory=False) for path in raw_paths],ignore_index=True);raw["fantrax_player_id"]=raw.fantrax_player_id.astype(str).str.strip().str.strip("*")
        detail=["fantrax_player_id","period","started_position","penalties_drawn","high_claims","smothers"]
        scoring_weekly=weekly.merge(raw.reindex(columns=detail).drop_duplicates(["fantrax_player_id","period"],keep="last"),on=["fantrax_player_id","period"],how="left")
    scoring_validation=build_scoring_validation(scoring_weekly,season,quality)
    identity=read(ROOT/"data/reference/whoscored_player_identity.csv"); managers=read(ROOT/f"data/reference/manager_observations_{season}.csv")
    if not managers.empty:
        lineup=lineup.merge(managers[["canonical_match_id","club_id","manager_id"]].drop_duplicates(["canonical_match_id","club_id"]),on=["canonical_match_id","club_id"],how="left")
    participation=build_player_match_participation(lineup,matches,weekly,understat,identity,season=season)
    starters=participation[participation.started]
    club_gate=starters.groupby(["canonical_match_id","club_id"]).size()
    gates={"starter_observations":int(len(starters)),"matches":int(starters.canonical_match_id.nunique()),"club_match_groups":int(len(club_gate)),"all_club_matches_have_11":bool(club_gate.eq(11).all()),"duplicate_player_match":bool(participation.duplicated(["canonical_match_id","canonical_player_id"]).any()),"starter_gate_pass":bool(len(starters)==220 and len(club_gate)==20 and club_gate.eq(11).all())}
    if season=="2627" and matches.canonical_match_id.nunique()==10 and not gates["starter_gate_pass"]:
        atomic_json(gates,quality/f"player_match_participation_gate_{season}.json"); raise ValueError(f"Starter quality gate failed: {gates}")
    atomic_csv(participation,model/f"player_match_participation_{season}.csv")
    xi=starters.merge(lineup[["canonical_match_id","canonical_player_id","whoscored_player_name","lineup_slot"]],on=["canonical_match_id","canonical_player_id"],how="left").sort_values(["date","club_id","lineup_slot"])
    atomic_csv(xi,quality/f"player_match_participation_gw1_{season}.csv")

    repaired=overlay_weekly_participation(weekly,participation)
    atomic_csv(repaired,model/f"current_player_weekly_{season}.csv")
    observed=participation[participation.appeared].copy()
    supp=read(advanced/f"supplemental_player_match_{season}.csv")
    metric_cols=["rating","goals","official_assists","key_passes","shots_on_target","dribbles_successful","tackles_won_derived","interceptions","clearances","aerial_wins","accurate_crosses_derived","cross_attempts","tackle_attempts","xg","xa","xgi","fantrax_points","ghost_points"]
    facts=supp[["canonical_match_id","canonical_player_id",*[c for c in metric_cols if c in supp]]].drop_duplicates(["canonical_match_id","canonical_player_id"])
    log=observed.merge(facts,on=["canonical_match_id","canonical_player_id"],how="left",validate="one_to_one")
    wcols=["fantrax_player_id","period","player_name","club","fantrax_position","current_manager_id","current_manager_name","roster_status","fantasy_points","ghost_points","assists","clean_sheets","goals","key_passes","shots_on_target","successful_dribbles","tackles_won","interceptions","clearances","aerials_won","accurate_crosses","xg","xa","xgi"]
    wf=weekly.reindex(columns=wcols).rename(columns={"period":"fantrax_period",**{c:f"weekly_{c}" for c in wcols[8:]}})
    log=log.merge(wf,on=["fantrax_player_id","fantrax_period"],how="left",validate="many_to_one",suffixes=("","_weekly"))
    rostered=log.current_manager_id.notna()
    choices={"fantrax_points":"weekly_fantasy_points","goals":"weekly_goals","key_passes":"weekly_key_passes","shots_on_target":"weekly_shots_on_target","successful_dribbles":"weekly_successful_dribbles","interceptions":"weekly_interceptions","clearances":"weekly_clearances","aerial_wins":"weekly_aerials_won","xg":"weekly_xg","xa":"weekly_xa","xgi":"weekly_xgi"}
    for target,fan in choices.items():
        provider=numeric(log,"dribbles_successful" if target=="successful_dribbles" else target); exact=numeric(log,fan).where(rostered)
        log[target]=exact.combine_first(provider); log[f"{target}_source"]=exact.notna().map({True:"FANTRAX_DETAILED",False:"WHOSCORED_OR_UNDERSTAT_OBSERVED"})
    log["assists"]=numeric(log,"weekly_assists").where(rostered).combine_first(numeric(log,"official_assists"))
    log["assist_source"]=numeric(log,"weekly_assists").where(rostered).notna().map({True:"FANTRAX_DETAILED",False:"WHOSCORED_OFFICIAL"})
    log["assist_semantics"]=rostered.map({True:"FANTRAX_FANTASY_ASSIST",False:"OFFICIAL_ASSIST"})
    log["clean_sheets"]=numeric(log,"clean_sheet_awarded_or_derived")
    log["tackles_won"]=numeric(log,"weekly_tackles_won").where(rostered).combine_first(numeric(log,"tackles_won_derived"))
    log["accurate_crosses"]=numeric(log,"weekly_accurate_crosses").where(rostered).combine_first(numeric(log,"accurate_crosses_derived"))
    authoritative=numeric(log,"weekly_ghost_points").where(rostered)
    ghost_rows=[];validation_rows=[]
    for index,row in log.iterrows():
        values={"fantasy_points":row.get("fantrax_points"),"position":row.get("fantrax_position"),"goals":row.get("goals"),"assists":row.get("assists"),"clean_sheets":row.get("clean_sheets"),"assist_semantics":row.get("assist_semantics"),"appeared":bool(row.get("appeared")),"season":season}
        resolved=derive_return_ghost(**values,exact_ghost=authoritative.loc[index]);derived=derive_return_ghost(**values)
        ghost_rows.append(resolved)
        exact=authoritative.loc[index];validation_rows.append({"canonical_player_id":row.get("canonical_player_id"),"player":row.get("player_name"),"club":row.get("club"),"position":row.get("fantrax_position"),"period":row.get("fantrax_period"),"FPts":row.get("fantrax_points"),"component_derived_ghost":exact,"derived_return_ghost":derived["ghost_points"],"difference":derived["ghost_points"]-exact if pd.notna(exact) and pd.notna(derived["ghost_points"]) else pd.NA,"goals":row.get("goals"),"assists":row.get("assists"),"clean_sheets":row.get("clean_sheets"),"goal_points_removed":derived["ghost_goal_points_removed"],"assist_points_removed":derived["ghost_assist_points_removed"],"cs_points_removed":derived["ghost_cs_points_removed"],"ghost_scoring_position":derived["ghost_scoring_position"],"ghost_source":resolved["ghost_points_source"],"assist_semantics":row.get("assist_semantics"),"fantrax_detailed_source_state":"AVAILABLE" if pd.notna(exact) else "UNAVAILABLE","notes":"FPts minus configured G/AT/CS only; peripheral scoring remains Ghost.","validation_status":"COMPARABLE" if pd.notna(exact) and pd.notna(derived["ghost_points"]) else "NOT_COMPARABLE"})
    ghost=pd.DataFrame(ghost_rows,index=log.index);log[ghost.columns]=ghost
    log["ghost_component_coverage"]=log["ghost_return_completeness"]
    atomic_csv(log,model/f"current_player_match_log_{season}.csv")

    totals=(log.groupby("fantrax_player_id",as_index=False).agg(games_played=("appeared","sum"),starts=("started","sum"),minutes=("minutes",lambda x:numeric(pd.DataFrame({"x":x}),"x").sum(min_count=1)),player_name=("player_name","last"),club=("club","last"),fantrax_position=("fantrax_position","last"),current_manager_name=("current_manager_name","last"),fantasy_points=("fantrax_points",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),ghost_points=("ghost_points",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),goals=("goals",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),assists=("assists",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),clean_sheets=("clean_sheets",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),key_passes=("key_passes",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),shots_on_target=("shots_on_target",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),successful_dribbles=("successful_dribbles",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),tackles_won=("tackles_won",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),interceptions=("interceptions",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),clearances=("clearances",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),aerial_wins=("aerial_wins",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),accurate_crosses=("accurate_crosses",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),xg=("xg",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),xa=("xa",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),xgi=("xgi",lambda x:pd.to_numeric(x,errors="coerce").sum(min_count=1)),rating=("rating","mean"),primary_observed_role=("tactical_role","last"),ghost_component_coverage=("ghost_component_coverage","mean")))
    # Preserve the complete current Fantrax player pool. Players with no observed
    # match receive zero participation denominators and therefore no rates.
    missing=weekly[~weekly.fantrax_player_id.astype(str).isin(totals.fantrax_player_id.astype(str))].drop_duplicates("fantrax_player_id")
    if not missing.empty:
        blank=pd.DataFrame({"fantrax_player_id":missing.fantrax_player_id.astype(str),"player_name":missing.player_name,"club":missing.club,"fantrax_position":missing.fantrax_position,"current_manager_name":missing.current_manager_name,"games_played":0,"starts":0,"minutes":0})
        totals=pd.concat([totals,blank],ignore_index=True)
    totals=add_canonical_rates(totals,("fantasy_points","ghost_points","goals","assists","clean_sheets","key_passes","shots_on_target","successful_dribbles","tackles_won","interceptions","clearances","aerial_wins","accurate_crosses","xg","xa","xgi"))
    totals=starter_observation_rates(totals,log)
    totals["start_percentage"]=numeric(totals,"starts")*100/numeric(totals,"games_played").where(numeric(totals,"games_played").gt(0))
    atomic_csv(totals,model/f"current_player_season_summary_{season}.csv")
    rate_quality=totals[["fantrax_player_id","player_name","games_played","starts","minutes","fantasy_points","fantasy_points_per_game","fantasy_points_per_start","fantasy_points_per_90","ghost_points","ghost_points_per_game","ghost_points_per_start","ghost_points_per_90"]]
    atomic_csv(rate_quality,quality/f"player_rate_validation_gw1_{season}.csv")
    atomic_csv(log[["fantrax_player_id","player_name","ghost_points","ghost_points_source","ghost_component_coverage"]],quality/f"ghost_component_audit_gw1_{season}.csv")
    validation=pd.DataFrame(validation_rows);atomic_csv(validation,quality/f"ghost_return_derivation_validation_{season}.csv");atomic_csv(validation[validation.validation_status.eq("COMPARABLE")&pd.to_numeric(validation.difference,errors="coerce").abs().gt(.01)],quality/f"ghost_return_derivation_mismatches_{season}.csv")
    coverage=log[["canonical_player_id","fantrax_player_id","player_name","club","fantrax_position","fantrax_period","fantrax_points","ghost_points","ghost_points_source","ghost_return_completeness","ghost_goal_points_removed","ghost_assist_points_removed","ghost_cs_points_removed","ghost_scoring_position"]].copy();coverage["methodology"]="official FPts minus configured goal, assist, and clean-sheet awards";atomic_csv(coverage,quality/f"ghost_derivation_coverage_{season}.csv")
    comparable=validation[validation.validation_status.eq("COMPARABLE")];diff=pd.to_numeric(comparable.difference,errors="coerce")
    atomic_json({"component_derived_ghost_observations":int(authoritative.notna().sum()),"derived_ghost_observations":int(log.ghost_points_source.astype(str).str.startswith("DERIVED").sum()),"waiver_derived_observations":int((~rostered&log.ghost_points_source.astype(str).str.startswith("DERIVED")).sum()),"partial_observations":int(log.ghost_points_source.eq("PARTIAL_DERIVED").sum()),"missing_observations":int(log.ghost_points_source.eq("MISSING").sum()),"comparable_component_observations":len(comparable),"exact_agreement":int(diff.abs().le(.01).sum()),"agreement_rate":float(diff.abs().le(.01).mean()) if len(diff) else None,"mae":float(diff.abs().mean()) if len(diff) else None,"median_absolute_difference":float(diff.abs().median()) if len(diff) else None,"total_component_derived_ghost":float(pd.to_numeric(comparable.component_derived_ghost,errors="coerce").sum()) if len(comparable) else None,"total_derived_ghost":float(pd.to_numeric(comparable.derived_return_ghost,errors="coerce").sum()) if len(comparable) else None,"mismatch_count":int(diff.abs().gt(.01).sum())},quality/f"ghost_return_derivation_summary_{season}.json")
    cs=log[rostered][["fantrax_player_id","player_name","fantrax_position","minutes","club_id","team_goals_against","weekly_clean_sheets","clean_sheets","clean_sheet_source"]]
    cs["exact_agreement"]=numeric(cs,"weekly_clean_sheets").eq(numeric(cs,"clean_sheets")); atomic_csv(cs,quality/f"clean_sheet_reconciliation_gw1_{season}.csv")
    j=totals[totals.player_name.str.contains("Janelt",case=False,na=False)]; atomic_csv(j,quality/f"janelt_canary_{season}.csv")
    atomic_json({**gates,"participation_rows":len(participation),"appeared":int(participation.appeared.sum()),"summary_players":len(totals),"janelt_fixed":bool(len(j) and j.starts.iloc[0]==1)},quality/f"player_participation_summary_{season}.json")
    print(json.dumps({**gates,"participation_rows":len(participation),"summary_players":len(totals)},indent=2)); return 0

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--season",default="2627");a=p.parse_args();raise SystemExit(main(a.season))
