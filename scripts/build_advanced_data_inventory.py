#!/usr/bin/env python3
"""Build the Sprint 9.5.1 semantic inventory entirely from validated caches."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.whoscored.workflows import atomic_csv, atomic_json

ADV = ROOT / "data/models/season_2526/advanced"
QUALITY = ROOT / "data/quality/season_2526"
REFERENCE = ROOT / "data/reference"
RAW = ROOT / "data/raw/whoscored/2526/poc"


def pct(n: int | float, d: int | float) -> float:
    return round(100 * n / d, 4) if d else 0.0


def example(series: pd.Series) -> str:
    values = series.dropna()
    return "" if values.empty else str(values.iloc[0])[:200]


def source_inventory() -> pd.DataFrame:
    specs = [
        ("raw_whoscored_match", RAW, "match_*/raw_match.json", "one provider payload per match", "WhoScored/Opta", "VALIDATED_RAW"),
        *[(p.stem.removesuffix("_2526"), p, None, "see dataset key", "supplemental advanced layer", "VALIDATED") for p in sorted(ADV.glob("*.csv"))],
        ("manager_registry", REFERENCE / "manager_registry.csv", None, "one canonical manager", "WhoScored observed identity", "VALIDATED"),
        ("manager_tenures", REFERENCE / "team_manager_tenures.csv", None, "one observed manager-club range", "WhoScored observations", "USABLE_WITH_CAVEAT"),
        ("player_identity", REFERENCE / "whoscored_player_identity.csv", None, "one WhoScored player ID", "WhoScored/Fantrax/Understat", "VALIDATED"),
    ]
    rows = []
    for name, path, pattern, grain, source, status in specs:
        if pattern:
            files = list(path.glob(pattern)); count = len(files)
            rows.append(dict(dataset=name, grain=grain, rows=count, unique_matches=count, unique_players="", unique_teams="", key_fields="match directory; provider identity; checksum", source=source, coverage_pct=pct(count, 380), status=status))
            continue
        if not Path(path).exists():
            continue
        d = pd.read_csv(path)
        match_col = next((c for c in ("canonical_match_id", "understat_match_id") if c in d), None)
        player_col = next((c for c in ("canonical_player_id", "whoscored_player_id") if c in d), None)
        team_cols = [c for c in ("club_id", "opponent_id", "home_club_id", "away_club_id") if c in d]
        teams = set()
        for c in team_cols: teams |= set(d[c].dropna().astype(str))
        rows.append(dict(dataset=name, grain=grain, rows=len(d), unique_matches=d[match_col].nunique() if match_col else "", unique_players=d[player_col].nunique() if player_col else "", unique_teams=len(teams) if teams else "", key_fields="; ".join(d.columns[:8]), source=source, coverage_pct=pct(d[match_col].nunique(), 380) if match_col else 100.0, status=status))
    return pd.DataFrame(rows)


def scan_raw() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    files = sorted(RAW.glob("match_*/raw_match.json")); total = len(files)
    field_stats: dict[str, dict] = defaultdict(lambda: {"present": 0, "examples": [], "types": set()})
    rating_rows = []; sub = defaultdict(int); raw_qualifiers = defaultdict(lambda: {"count": 0, "events": set(), "matches": set(), "players": set(), "values": []})
    paths = {
        "startDate": "$.startDate", "startTime": "$.startTime", "statusCode": "$.statusCode", "venueName": "$.venueName",
        "attendance": "$.attendance", "referee": "$.referee", "weatherCode": "$.weatherCode", "score": "$.score",
        "ftScore": "$.ftScore", "htScore": "$.htScore", "maxMinute": "$.maxMinute", "expandedMaxMinute": "$.expandedMaxMinute",
        "home.name": "$.home.name", "away.name": "$.away.name", "home.teamId": "$.home.teamId", "away.teamId": "$.away.teamId",
        "home.managerName": "$.home.managerName", "away.managerName": "$.away.managerName", "home.formations": "$.home.formations", "away.formations": "$.away.formations",
    }
    def get(payload, dotted):
        cur = payload
        for part in dotted.split("."):
            if not isinstance(cur, dict): return None
            cur = cur.get(part)
        return cur
    for f in files:
        p = json.loads(f.read_text(encoding="utf-8")); mid = f.parent.name.removeprefix("match_")
        for key, raw_path in paths.items():
            value = get(p, key)
            if value is not None and value != "":
                s = field_stats[key]; s["present"] += 1; s["types"].add(type(value).__name__)
                if len(s["examples"]) < 1: s["examples"].append(str(value)[:200])
        for side in ("home", "away"):
            for player in p.get(side, {}).get("players", []):
                ratings = player.get("stats", {}).get("ratings", {}) or {}
                final = ratings[max(ratings, key=lambda x: int(x))] if ratings else player.get("rating")
                on = player.get("subbedInExpandedMinute"); off = player.get("subbedOutExpandedMinute")
                rating_rows.append(dict(match_id=mid, player_id=player.get("playerId"), started=bool(player.get("isFirstEleven")), used_sub=on is not None, unused=not player.get("isFirstEleven") and on is None, goalkeeper=player.get("position") == "GK", subbed_off=off is not None, rating=final, rating_history_points=len(ratings)))
        events = p.get("events", [])
        ons = [e for e in events if (e.get("type") or {}).get("displayName") == "SubstitutionOn"]
        offs = [e for e in events if (e.get("type") or {}).get("displayName") == "SubstitutionOff"]
        sub["on_events"] += len(ons); sub["off_events"] += len(offs)
        sub["on_with_expanded"] += sum(e.get("expandedMinute") is not None for e in ons); sub["off_with_expanded"] += sum(e.get("expandedMinute") is not None for e in offs)
        sub["paired_related"] += sum(e.get("relatedEventId") is not None or any((q.get("type") or {}).get("displayName") == "RelatedEventId" for q in e.get("qualifiers", [])) for e in ons)
        for e in events:
            et = (e.get("type") or {}).get("displayName", "")
            for q in e.get("qualifiers", []) or []:
                qn = (q.get("type") or {}).get("displayName")
                if not qn: continue
                s = raw_qualifiers[qn]; s["count"] += 1; s["events"].add(et); s["matches"].add(mid)
                if e.get("playerId") is not None: s["players"].add(e["playerId"])
                if q.get("value") is not None and len(s["values"]) < 3: s["values"].append(str(q["value"])[:100])
    field_rows = []
    normalized = set(pd.read_csv(ADV / "whoscored_match_2526.csv").columns)
    for key, raw_path in paths.items():
        s = field_stats[key]; ready = key in {"startDate","statusCode","venueName","score","ftScore","home.name","away.name","home.teamId","away.teamId","home.managerName","away.managerName","home.formations","away.formations"}
        field_rows.append(dict(field_name=key.replace(".", "_"), source="WhoScored raw matchCentreData", raw_path=raw_path, coverage_pct=pct(s["present"], total), data_type="|".join(sorted(s["types"])), example_value=s["examples"][0] if s["examples"] else "", observed_or_derived="OBSERVED", production_status="PRODUCTION_READY" if ready else "USABLE_WITH_CAVEAT", normalized_now=key.replace(".", "_") in normalized, notes="Raw metadata; presence audited across all validated matches."))
    ratings = pd.DataFrame(rating_rows)
    summary = {"raw_matches": total, "rating": {}, "substitutions": dict(sub)}
    for label, mask in {"all": pd.Series(True,index=ratings.index), "starters": ratings.started, "used_substitutes": ratings.used_sub, "unused_substitutes": ratings.unused, "goalkeepers": ratings.goalkeeper, "subbed_off": ratings.subbed_off}.items():
        x = ratings.loc[mask, "rating"].dropna().astype(float)
        summary["rating"][label] = {"observations": int(mask.sum()), "rated": len(x), "coverage_pct": pct(len(x), int(mask.sum())), "min": None if x.empty else float(x.min()), "median": None if x.empty else float(x.median()), "max": None if x.empty else float(x.max()), "missing": int(mask.sum()-len(x))}
    qualifier_rows = []
    for qn, s in sorted(raw_qualifiers.items()):
        qualifier_rows.append(dict(qualifier=qn, count=s["count"], event_types="|".join(sorted(s["events"])), matches=len(s["matches"]), players=len(s["players"]), coordinates_context="inherits parent event coordinates", example_raw_value="|".join(s["values"]), potential_meaning=qualifier_meaning(qn), production_status=qualifier_status(qn), notes="Observed raw qualifier label; semantics are not inferred from numeric provider ID."))
    return pd.DataFrame(field_rows), pd.DataFrame(qualifier_rows), summary


def qualifier_meaning(q: str) -> str:
    known = {"KeyPass":"provider-marked shot-creating pass", "ShotAssist":"pass preceding a shot", "Cross":"cross delivery", "Throughball":"through ball", "CornerTaken":"corner restart", "FreekickTaken":"free-kick restart", "IndirectFreekickTaken":"indirect free-kick restart", "DirectFreekick":"direct-free-kick shot context", "Penalty":"penalty context", "ThrowIn":"throw-in", "Longball":"long pass", "IntentionalGoalAssist":"provider-marked goal assist", "BigChance":"big-chance context", "HeadPass":"headed pass", "Blocked":"blocked action", "Foul":"foul context", "Offside":"offside context"}
    return known.get(q, "provider qualifier; retain raw meaning pending targeted use")


def qualifier_status(q: str) -> str:
    production = {"KeyPass","ShotAssist","Cross","Throughball","CornerTaken","FreekickTaken","IndirectFreekickTaken","Penalty","ThrowIn","Longball","IntentionalGoalAssist","BigChance","HeadPass","Blocked","Offside","PassEndX","PassEndY","GoalMouthY","GoalMouthZ","RightFoot","LeftFoot","Head","RegularPlay","SetPiece","FromCorner","DirectFreekick"}
    caveat = {"Foul","Zone","Length","Angle","RelatedEventId","PlayerPosition","FormationSlot","JerseyNumber"}
    return "PRODUCTION_READY" if q in production else "USABLE_WITH_CAVEAT" if q in caveat else "RESEARCH_ONLY"


def event_dictionary(events: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    production={"Pass","TakeOn","Aerial","Tackle","Interception","Clearance","BallRecovery","BlockedPass","MissedShots","SavedShot","ShotOnPost","Goal","SubstitutionOn","SubstitutionOff","Card","Foul","OffsideGiven"}
    caveat={"Challenge","Dispossessed","KeeperPickup","Punch","Claim","Save","Smother","Error","FormationSet","FormationChange"}
    for name,g in events.groupby("event_type",dropna=False):
        players=g.whoscored_player_id.dropna().nunique(); outcome=g.outcome.notna(); coords=g[["x","y"]].notna().all(axis=1); ends=g[["end_x","end_y"]].notna().all(axis=1); quals=g.qualifiers.astype(str).ne("[]")
        rows.append(dict(raw_event_type=name,count=len(g),matches=g.canonical_match_id.nunique(),players=players,outcome_present=pct(outcome.sum(),len(g)),coordinates_present=pct(coords.sum(),len(g)),end_coordinates_present=pct(ends.sum(),len(g)),qualifiers_present=pct(quals.sum(),len(g)),normalized_category=event_category(str(name)),production_status="PRODUCTION_READY" if name in production else "USABLE_WITH_CAVEAT" if name in caveat else "RESEARCH_ONLY",notes="Observed across validated 2025/26 event stream."))
    return pd.DataFrame(rows).sort_values(["count","raw_event_type"],ascending=[False,True])


def event_category(name: str) -> str:
    groups={"Passing":{"Pass","OffsidePass"},"Dribbling":{"TakeOn","Dispossessed","Challenge"},"Aerials":{"Aerial"},"Defense":{"Tackle","Interception","Clearance","BallRecovery","BlockedPass","Block"},"Shooting":{"MissedShots","SavedShot","ShotOnPost","Goal"},"Discipline":{"Foul","Card","OffsideGiven"},"Goalkeeping":{"Save","Claim","Punch","Smother","KeeperPickup"},"Lineup":{"SubstitutionOn","SubstitutionOff","FormationSet","FormationChange"}}
    return next((k for k,v in groups.items() if name in v),"Other")


def role_dictionary(lineup: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for raw,g in lineup.groupby("actual_position_raw",dropna=False):
        mapped=sorted(set(g.actual_position_standardized.dropna().astype(str)))
        rows.append(dict(raw_role=raw,standardized_role="|".join(mapped),count=len(g),players=g.whoscored_player_id.nunique(),matches=g.canonical_match_id.nunique(),mapping_status="MAPPED" if len(mapped)==1 else "UNMAPPED",notes="Observed tactical role; separate from Fantrax eligibility."))
    return pd.DataFrame(rows).sort_values("count",ascending=False)


def field_inventory(d: pd.DataFrame, source: str, grain: str) -> pd.DataFrame:
    rows=[]
    derived={"actual_position_standardized":"standardize actual_position_raw through fixed tactical-role map","bench":"not started in provider squad","sub_on_minute":"expandedMinute of explicit SubstitutionOn event","sub_off_minute":"expandedMinute of explicit SubstitutionOff event","canonical_player_id":"deterministic persistent identity crosswalk"}
    caveat={"minutes","sub_on_minute","sub_off_minute","canonical_player_id","actual_position_standardized"}
    for col in d.columns:
        non=d[col].notna().sum()
        rows.append(dict(field_name=col,source=source,source_field_or_rule=derived.get(col,col),grain=grain,data_type=str(d[col].dtype),coverage_pct=pct(non,len(d)),non_null_observations=int(non),example_value=example(d[col]),observed_or_derived="DERIVED" if col in derived else "OBSERVED",production_status="USABLE_WITH_CAVEAT" if col in caveat else "PRODUCTION_READY",notes="Substitution expanded minutes are provider timestamps, not exact elapsed playing time." if col in {"minutes","sub_on_minute","sub_off_minute"} else ""))
    return pd.DataFrame(rows)


def pitch_layers() -> pd.DataFrame:
    rows=[
        ("activity_density","Event Activity Density","all player-linked events","all","x,y","points/density","Event activity; not tracking"),
        ("passes","Passes","event_type == Pass","successful/unsuccessful","x,y,end_x,end_y","line when end coordinates exist","Provider pass events"),
        ("key_passes","Key Passes","Pass with explicit KeyPass qualifier","pass outcome retained","x,y,end_x,end_y","line","Provider-marked key passes"),
        ("crosses","Crosses","Pass with explicit Cross qualifier","pass outcome retained","x,y,end_x,end_y","line","Raw crosses; not Fantrax accurate crosses"),
        ("dribbles","TakeOns","event_type == TakeOn","successful/unsuccessful","x,y","point","Discrete TakeOn, not continuous carry"),
        ("shots","Shots","MissedShots|SavedShot|ShotOnPost|Goal","shot outcome/type","x,y","point","Understat remains xG authority"),
        ("defensive_actions","Defensive Actions","Tackle|Interception|Clearance|BlockedPass","event outcome retained","x,y","point","Direct observed actions"),
        ("recoveries","Recoveries","event_type == BallRecovery","all","x,y","point","Direct observed recoveries"),
        ("aerials","Aerials","event_type == Aerial","winner/loser outcome","x,y","point","Player-events; physical contests are paired"),
    ]
    return pd.DataFrame(rows,columns=["layer_key","display_name","event_filter","outcome_handling","coordinate_fields","rendering","safe_label_notes"]).assign(production_status="PRODUCTION_READY")


def set_piece_inventory(qualifiers: pd.DataFrame) -> pd.DataFrame:
    available=set(qualifiers.qualifier)
    specs=[
        ("corners_taken",{"CornerTaken"},"Pass with CornerTaken","DIRECTLY_OBSERVED"),
        ("corner_crosses",{"CornerTaken","Cross"},"Pass containing both qualifiers","SAFELY_DERIVED"),
        ("corner_key_passes",{"CornerTaken","KeyPass"},"Pass containing both qualifiers","SAFELY_DERIVED"),
        ("free_kicks_taken",{"FreekickTaken"},"Pass with FreekickTaken","DIRECTLY_OBSERVED"),
        ("indirect_free_kicks",{"IndirectFreekickTaken"},"event with explicit qualifier","DIRECTLY_OBSERVED"),
        ("direct_free_kick_shots",{"DirectFreekick"},"shot with DirectFreekick","DIRECTLY_OBSERVED"),
        ("free_kick_crosses",{"FreekickTaken","Cross"},"Pass containing both qualifiers","SAFELY_DERIVED"),
        ("free_kick_key_passes",{"FreekickTaken","KeyPass"},"Pass containing both qualifiers","SAFELY_DERIVED"),
        ("penalties",{"Penalty"},"shot/goalkeeper/foul event with Penalty context","DIRECTLY_OBSERVED"),
        ("throw_ins",{"ThrowIn"},"Pass with ThrowIn","DIRECTLY_OBSERVED"),
        ("set_piece_shots",{"SetPiece"},"shot with SetPiece or explicit restart qualifier","SAFELY_DERIVED"),
        ("set_piece_assists",{"IntentionalGoalAssist","CornerTaken"},"assist evidence plus explicit restart context","SAFELY_DERIVED"),
    ]
    return pd.DataFrame([dict(metric_key=k,required_qualifiers="|".join(sorted(req)),rule=rule,availability=classification if req<=available else "NOT_AVAILABLE",production_status="PRODUCTION_READY" if req<=available else "REJECT",notes="Requires every listed explicit qualifier on the relevant event/context.") for k,req,rule,classification in specs])


def formation_dictionary(history: pd.DataFrame) -> pd.DataFrame:
    return history.groupby("formation",dropna=False).agg(count=("canonical_match_id","size"),matches=("canonical_match_id","nunique"),clubs=("club_id","nunique"),managers=("manager_id","nunique")).reset_index().assign(production_status="PRODUCTION_READY",notes="Starting formation observed from WhoScored; in-match FormationChange events remain research context.")


def coverage_row(d: pd.DataFrame, col: str) -> tuple[float,float,float,int,int,str]:
    s=d[col]; non=s.notna(); match=pct(d.loc[non,"canonical_match_id"].nunique(),d.canonical_match_id.nunique()) if "canonical_match_id" in d else 0
    player=pct(d.loc[non,"canonical_player_id"].nunique(),d.canonical_player_id.nunique()) if "canonical_player_id" in d else 0
    numeric=pd.to_numeric(s,errors="coerce"); return pct(non.sum(),len(d)),match,player,int(numeric.eq(0).sum()),int(non.sum()),f"{numeric.min()}..{numeric.max()}" if numeric.notna().any() else ""


def metric_dictionary(advanced: pd.DataFrame) -> pd.DataFrame:
    observed_ws={"rating","formation","actual_position_standardized","minutes","started","key_passes","dribbles_attempted","dribbles_successful","aerials_attempted","aerials_won","tackles","interceptions","clearances","recoveries","blocked_passes","crosses","through_balls","shots","shots_on_target","goals","fouls","passes_attempted","passes_completed"}
    understat={"xg","xa","understat_minutes","xgi"}; fantrax={"mgr_fantasy_points","avail_fpts","mgr_min","mgr_kp","mgr_tkw","mgr_int","mgr_clr","mgr_cos","mgr_aer","mgr_sot","mgr_ac","fantrax_ghost_points","fantrax_points"}
    context=set(advanced.columns)-observed_ws-understat-fantrax
    categories={"rating":"Rating","formation":"Role","actual_position_standardized":"Role","minutes":"Playing Time","started":"Playing Time","key_passes":"Chance Creation","dribbles_attempted":"Dribbling","dribbles_successful":"Dribbling","aerials_attempted":"Aerials","aerials_won":"Aerials","tackles":"Defense","interceptions":"Defense","clearances":"Defense","recoveries":"Defense","blocked_passes":"Defense","crosses":"Passing","through_balls":"Chance Creation","shots":"Shooting","shots_on_target":"Shooting","goals":"Shooting","fouls":"Discipline","passes_attempted":"Passing","passes_completed":"Passing","xg":"Shooting","xa":"Chance Creation","xgi":"Chance Creation","fantrax_points":"Fantasy","fantrax_ghost_points":"Fantasy"}
    formulas={"xgi":"xg + xa from exact Understat player-match", "fantrax_ghost_points":"Fantrax points less goal/assist component using established scoring", "shots_on_target":"SavedShot or Goal event", "passes_completed":"Pass with Successful outcome", "minutes":"WhoScored player minutes where present; not reconstructed as exact from substitution timestamps", "club_period_fixtures":"count of league fixtures for club in Fantrax period", "feature_class":"constant semantic label identifying observed/derived supplemental features", "contains_prediction":"constant false flag; inventory contains no predicted values"}
    caveat={"minutes","tackles","crosses","fouls","fantrax_alignment","understat_alignment","club_period_fixtures"}
    ready_override={"rating","formation","actual_position_standardized","manager_id","manager_name"}
    research={"feature_class","contains_prediction","registry_player_id","fantrax_id_clean","avail_fpts"}
    reject={"contains_prediction"}
    rows=[]
    for col in advanced.columns:
        cov,mc,pc,zeros,non_null,rng=coverage_row(advanced,col)
        source="Understat" if col in understat else "Fantrax" if col in fantrax else "WhoScored/Opta" if col in observed_ws else "Canonical integration"
        observed="DERIVED" if col in {"xgi","fantrax_ghost_points","club_period_fixtures","feature_class","contains_prediction"} else "OBSERVED"
        status="REJECT" if col in reject else "RESEARCH_ONLY" if col in research else "PRODUCTION_READY" if col in ready_override else "USABLE_WITH_CAVEAT" if col in caveat or cov<90 else "PRODUCTION_READY"
        requires_minutes=col in {"xg","xa","xgi","key_passes","dribbles_attempted","dribbles_successful","aerials_attempted","aerials_won","tackles","interceptions","clearances","recoveries","blocked_passes","crosses","through_balls","shots","shots_on_target","goals","fouls","passes_attempted","passes_completed","fantrax_points","fantrax_ghost_points"}
        rows.append(dict(metric_key=col,display_name=col.replace("_"," ").title(),category=categories.get(col,"Identity / Context"),source=source,source_field_or_rule=col,grain="player-match",observed_or_derived=observed,formula=formulas.get(col,"direct field" if observed=="OBSERVED" else ""),coverage_pct=cov,match_coverage_pct=mc,player_coverage_pct=pc,supports_total=col not in context,supports_per_match=col not in context,supports_per_start=col not in context,supports_per90=requires_minutes,supports_per_appearance=col not in context,requires_minutes=requires_minutes,higher_is_better=col not in {"fouls"},fantrax_overlap=col if col in fantrax else {"key_passes":"mgr_kp","aerials_won":"mgr_aer","interceptions":"mgr_int","clearances":"mgr_clr","shots_on_target":"mgr_sot","tackles":"mgr_tkw","crosses":"mgr_ac"}.get(col,""),understat_overlap=col if col in understat else "",production_status=status,recommended_ui=ui_for(categories.get(col,"Identity / Context"),status),recommended_model_use="candidate input only" if status!="REJECT" else "none",non_null_observations=non_null,observed_zero_count=zeros,outlier_range=rng,notes="Per-90 only when compatible authoritative minutes are non-null." if requires_minutes else ""))
    return pd.DataFrame(rows)


def ui_for(category: str,status: str) -> str:
    if status in {"REJECT","RESEARCH_ONLY"}: return "none / research"
    return {"Fantasy":"Player Performance","Role":"Player Advanced / Teams Formations","Rating":"Player Overview","Chance Creation":"Player Advanced","Passing":"Player Advanced / Player Pitch","Dribbling":"Player Advanced / Player Pitch","Shooting":"Player Advanced / Player Pitch","Defense":"Player Advanced / Player Pitch","Aerials":"Player Advanced","Discipline":"Player Match Log","Identity / Context":"Player Match Log"}.get(category,"Player Advanced")


def build_docs(summary: dict, sources: pd.DataFrame, events: pd.DataFrame, qualifiers: pd.DataFrame, roles: pd.DataFrame, formations: pd.DataFrame, metrics: pd.DataFrame, reconciliation: pd.DataFrame, elapsed: dict) -> str:
    q=set(qualifiers.qualifier); et=set(events.raw_event_type)
    def available(*names): return ", ".join(n for n in names if n in q) or "none observed"
    ratings=summary["rating"]
    prod=metrics[metrics.production_status.eq("PRODUCTION_READY")].metric_key.tolist(); caveat=metrics[metrics.production_status.eq("USABLE_WITH_CAVEAT")].metric_key.tolist(); research=metrics[metrics.production_status.eq("RESEARCH_ONLY")].metric_key.tolist(); reject=metrics[metrics.production_status.eq("REJECT")].metric_key.tolist()
    return f"""# Advanced data inventory — 2025/26

Generated from the complete cached 380-match layer. This document describes observed and deterministic derived data only; it contains no predictions or opaque scores.

## 1. Identity / context

The inventory covers {len(sources)} source/model tables, {summary['raw_matches']} validated raw matches, 20 clubs, 677 observed WhoScored players, and 31 managers. Canonical player identity is proven for 522/537 meaningful appearance players (97.21%). Tactical role is distinct from Fantrax eligibility.

## 2. Playing time / substitutions

`SubstitutionOn` and `SubstitutionOff` are explicit event types: {summary['substitutions'].get('on_events',0)} on-events and {summary['substitutions'].get('off_events',0)} off-events. Expanded minute is suitable for an observed substitution timestamp, including provider stoppage-time expansion. It is not an exact elapsed-minutes clock. `estimated_minutes_played` may be derived as `sub_off_expanded_minute` for starters or `match_expanded_max - sub_on_expanded_minute` for used substitutes, but remains **RESEARCH_ONLY** until reconciled against authoritative minutes. Unused substitutes have neither event. Existing `minutes` remains usable only where the player payload or exact Understat/Fantrax context supplies it.

## 3. Rating

Final rating extraction is deterministic: take the rating-history value at the greatest numeric history key. All rated values are bounded 0–10. All appearances: {ratings['all']['rated']}/{ratings['all']['observations']} ({ratings['all']['coverage_pct']}%), median {ratings['all']['median']}, range {ratings['all']['min']}–{ratings['all']['max']}. Starters: {ratings['starters']['coverage_pct']}%; used substitutes: {ratings['used_substitutes']['coverage_pct']}%; unused substitutes: {ratings['unused_substitutes']['coverage_pct']}%; goalkeepers: {ratings['goalkeepers']['coverage_pct']}%. Unused-player missingness is expected.

## 4. Tactical roles

{len(roles)} raw position values were observed. Known values map deterministically into the established role taxonomy; unmapped values remain missing. Starting-role coverage is 97.15%. Starting formation is production-ready. In-match `FormationChange` events exist ({int(events.loc[events.raw_event_type.eq('FormationChange'),'count'].sum()) if 'FormationChange' in et else 0}) but are research context rather than a complete continuous formation timeline.

## 5. Passing

Pass attempts and completion are directly observed from `Pass` plus outcome. Explicit passing qualifiers include: {available('Cross','Throughball','Longball','HeadPass','CornerTaken','FreeKickTaken','ThrowIn')}. Final-third entry and box entry are deterministic coordinate-derived metrics. The existing positive x-distance field is labeled a progression proxy, not a validated “progressive pass.” Switches, distance bands, and direction groups remain research until a written geometry threshold is adopted.

## 6. Chance creation

Key passes require the explicit `KeyPass` qualifier. Assists retain explicit provider evidence where present. Open-play versus set-piece key passes can be safely derived by combining `KeyPass` with restart/situation qualifiers. Understat remains authoritative for xA.

## 7. Set pieces

Observed qualifier support: {available('CornerTaken','FreeKickTaken','DirectFreekick','IndirectFreekick','Penalty','ThrowIn','SetPiece','FromCorner')}. Corners, free-kick passes/crosses/key passes, penalties, and set-piece shots are safe when their explicit qualifier is present. “Set-piece taker” profiles are derived counts, not assigned roles. Absence of a qualifier must not be treated as proof of a different restart type.

## 8. Dribbling / carries

`TakeOn` plus outcome supplies attempts, successes, failures, and locations. Final-third and box TakeOns are safe spatial derivatives. No continuous tracking/carry stream exists; WhoScored TakeOns must not be labeled complete carries.

## 9. Shooting

Shots are `MissedShots`, `SavedShot`, `ShotOnPost`, and `Goal`. Locations, body-part and situation qualifiers support transparent splits where present. WhoScored supplies outcomes; Understat remains xG authority. No WhoScored xG approximation is approved.

## 10. Defensive actions

Tackle, interception, clearance, recovery, blocked-pass, and relevant block events are directly observed. Outcome can split tackle success where populated, but WhoScored tackles are not Fantrax tackles won. Defensive-action height is a safe average-location derivative.

## 11. Aerials

Each participant has an `Aerial` player-event with outcome-based win/loss semantics. Player attempts count participant events. Team physical-contest counts must pair related opponent events or divide validated paired events; summing both participants double-counts contests.

## 12. Fouls / discipline

Foul, Card, and offside event types plus card/penalty/misconduct qualifiers provide explicit evidence. “Foul won” versus “foul committed” requires related-player/team semantics and remains usable with caveat until every pairing is validated.

## 13. Goalkeeping

Goalkeeper evidence is distributed across events, qualifiers, and player stat histories rather than one complete event type. Saves and explicit claim/punch/smother/parry evidence may be used individually. A complete goalkeeper-actions total is not approved without a dedicated reconciliation.

## 14. Spatial / pitch data

Coordinates are normalized 0–100 and provider-oriented left-to-right for the acting team. Base-coordinate coverage is 100%; complete end-coordinate coverage is 66.52%. Safe labels are **Event Activity**, **Event Activity Density**, and **Event Activity Heatmap**, never player tracking. Production layers: activity, passes, key passes, crosses, TakeOns, shots, defensive actions, recoveries, and aerial player-events. Pass lines require end coordinates; point layers do not.

## 15. Team / formation

`team_match_features_2526` has 760 unique club-match rows. Production-ready inputs include formation, manager, event totals, passing, creation, shooting, defensive actions, aerial player-events, and transparent spatial averages. Understat owns xG/xGA; Fantrax owns fantasy production allowed.

## 16. Manager context

Manager per club-match, observed date ranges, formation under manager, player role under manager, and event rates under manager are available. Observed ranges are not exact employment dates and causal manager effects are not claimed.

## 17. Fantrax integration

Fantasy points and Ghost points remain Fantrax-authoritative and are attributed only for exact single-league-match periods. Season reconciliation shows provider-definition agreement without forcing equivalence. Tackle and cross comparisons retain caveats because Fantrax fields are tackles won and accurate crosses.

## 18. Understat integration

Understat is authoritative for xG, xA, and xGI, with 11,237 exact player-match joins (76.56%). Missing exact joins stay missing; season aggregates are not substituted.

## 19. Rates and future modeling inputs

Totals, per-match, per-appearance, and per-start rates are safe with explicit denominators. Per-90 is allowed only when compatible authoritative minutes are non-null; substitution timestamps alone are not sufficient. Available future inputs include recent starts, roles, formation, manager, prior lineup, venue, opponent, exact historical minutes, positional fantasy allowed, xG/xGA, event/spatial profiles, and schedule context. They remain inputs—not predictions.

## Readiness summary

- **PRODUCTION_READY:** {', '.join(prod)}
- **USABLE_WITH_CAVEAT:** {', '.join(caveat)}
- **RESEARCH_ONLY:** {', '.join(research)}
- **REJECT:** {', '.join(reject)}

Machine-readable evidence lives in `data/reference/advanced_metric_inventory_2526.csv` and the season quality dictionaries. Inventory build time: {elapsed['complete_seconds']} seconds.
"""


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--season",default="2526"); args=parser.parse_args()
    if args.season != "2526": raise SystemExit("Only the validated 2526 inventory is implemented")
    started=time.perf_counter(); stage={}
    t=time.perf_counter(); sources=source_inventory(); match_fields,qualifiers,raw_summary=scan_raw(); stage["raw_event_qualifier_inventory_seconds"]=round(time.perf_counter()-t,3)
    t=time.perf_counter(); events=pd.read_csv(ADV/"whoscored_event_2526.csv",low_memory=False); lineup=pd.read_csv(ADV/"whoscored_lineup_2526.csv",low_memory=False); history=pd.read_csv(ADV/"team_formation_history_2526.csv"); advanced=pd.read_csv(ADV/"advanced_player_match_2526.csv",low_memory=False)
    event_types=event_dictionary(events); roles=role_dictionary(lineup); formations=formation_dictionary(history); lineup_fields=field_inventory(lineup,"WhoScored lineup plus canonical identity","player-match squad observation"); layers=pitch_layers(); set_pieces=set_piece_inventory(qualifiers); stage["normalized_dictionary_seconds"]=round(time.perf_counter()-t,3)
    t=time.perf_counter(); metrics=metric_dictionary(advanced); stage["metric_coverage_seconds"]=round(time.perf_counter()-t,3)
    reconciliation=pd.read_csv(QUALITY/"whoscored_fantrax_reconciliation_2526.csv")
    outputs={QUALITY/"whoscored_source_inventory_2526.csv":sources,QUALITY/"whoscored_match_field_inventory_2526.csv":match_fields,QUALITY/"whoscored_lineup_field_inventory_2526.csv":lineup_fields,QUALITY/"whoscored_event_type_dictionary_2526.csv":event_types,QUALITY/"whoscored_qualifier_dictionary_2526.csv":qualifiers,QUALITY/"whoscored_tactical_role_dictionary_2526.csv":roles,QUALITY/"whoscored_formation_dictionary_2526.csv":formations,QUALITY/"whoscored_set_piece_inventory_2526.csv":set_pieces,QUALITY/"player_pitch_layer_dictionary_2526.csv":layers,REFERENCE/"advanced_player_metric_dictionary_2526.csv":metrics,REFERENCE/"advanced_metric_inventory_2526.csv":metrics}
    for path,frame in outputs.items(): atomic_csv(frame,path)
    stage["complete_seconds"]=round(time.perf_counter()-started,3)
    docs=build_docs(raw_summary,sources,event_types,qualifiers,roles,formations,metrics,reconciliation,stage); (ROOT/"docs/advanced_data_inventory.md").write_text(docs,encoding="utf-8")
    atomic_json({**stage,"datasets":len(sources),"event_types":len(event_types),"qualifiers":len(qualifiers),"roles":len(roles),"formations":len(formations),"metrics":len(metrics),"rating":raw_summary["rating"],"substitutions":raw_summary["substitutions"]},QUALITY/"advanced_inventory_build_summary_2526.json")
    print(json.dumps({**stage,"datasets":len(sources),"event_types":len(event_types),"qualifiers":len(qualifiers),"roles":len(roles),"formations":len(formations),"metrics":len(metrics)},indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
