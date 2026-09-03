"""Controlled player comparison metric catalog and radar presets."""
from __future__ import annotations
from dataclasses import dataclass

MODES=("Projection","Historical","Current Season","Draft Profile","Custom")
RATE_BASES=("Total","Per Game","Per Start","Per 90")
PERCENTILE_BASES=("League","Position")

@dataclass(frozen=True)
class Metric:
    key: str; label: str; family: str; fields: dict[str,str]; unit: str="number"; digits: int=1
    higher_is_better: bool=True; modes: tuple[str,...]=MODES; percentile: bool=True
    position_percentile: bool=True; missing: str="—"; minimum: str="valid numeric value"; source: str="live_player_analytics"
    @property
    def rate_bases(self)->tuple[str,...]: return tuple(self.fields)
    def field_for(self,basis:str)->str: return self.fields.get(basis) or self.fields.get("Natural") or next(iter(self.fields.values()))
    def label_for(self,basis:str)->str:
        suffix={"Per Game":" / Game","Per Start":" / Start","Per 90":" / 90"}.get(basis,"") if basis in self.fields else ""
        return self.label+suffix

def _m(key,label,family,field,*,modes=MODES,unit="number",digits=1,higher=True,source="live_player_analytics",**rates):
    return Metric(key,label,family,{"Natural":field,**rates},unit,digits,higher,modes,source=source)

CATALOG={m.key:m for m in (
 _m("projected_points","Projected Points","Projection","fantrax_projected_points",modes=("Projection","Draft Profile","Custom")),
 _m("projected_minutes","Projected Minutes","Playing Time","projected_minutes_percentage",modes=("Projection","Draft Profile","Custom"),unit="percent"),
 _m("minutes_confidence","Minutes Confidence","Playing Time","minutes_confidence",modes=("Projection","Draft Profile","Custom"),unit="percent"),
 _m("club_strength","Club Strength","Club Context","team_strength_percentile",modes=("Projection","Draft Profile","Custom"),unit="percent"),
 _m("fixture_ease","Fixture Ease","Fixture Context","next_five_fixture_ease_percentile",modes=("Projection","Current Season","Draft Profile","Custom"),unit="percent"),
 _m("draft_score","Draft Score","Draft Context","draft_score",modes=("Projection","Draft Profile","Custom")),
 _m("draft_value","Draft Value vs ADP","Draft Context","value_vs_adp",modes=("Draft Profile","Custom")),
 _m("adp","ADP","Draft Context","adp",modes=("Draft Profile","Custom"),higher=False),
 _m("draft_rank","Draft Rank","Draft Context","draft_rank",modes=("Draft Profile","Custom"),higher=False,digits=0),
 Metric("fantasy_production","Fantasy Production","Fantasy Production",{"Total":"historical_fantasy_points","Per Game":"historical_points_per_appearance","Per Start":"historical_points_per_start","Per 90":"historical_points_per_90"},modes=("Historical","Custom"),source="2025/26 fantasy history"),
 Metric("ghost_floor","Ghost Floor","Ghost Floor",{"Total":"historical_ghost_points","Per Game":"historical_ghost_per_appearance","Per Start":"historical_ghost_per_start","Per 90":"historical_ghost_per_90"},modes=("Historical","Custom"),source="2025/26 fantasy history"),
 Metric("xgi","xGI","Attacking Output",{"Total":"historical_xgi","Per 90":"historical_xgi_per_90"},digits=2,modes=("Historical","Custom"),source="Understat 2025/26"),
 _m("start_rate","Start Rate","Playing Time","historical_start_percentage",modes=("Historical","Custom"),unit="percent"),
 _m("historical_minutes","Historical Minutes","Playing Time","historical_minutes",modes=("Historical","Custom"),digits=0),
 _m("historical_starts","Historical Starts","Playing Time","historical_starts",modes=("Historical","Custom"),digits=0),
 _m("historical_season_points","Season Points","Fantasy Production","historical_fantasy_points",modes=("Historical","Custom"),source="Finalized 2025/26 fantasy history"),
 _m("historical_fp90","Fantasy Points / 90","Fantasy Production","historical_points_per_90",modes=("Historical","Custom"),source="Finalized 2025/26 fantasy history"),
 _m("historical_fpstart","Fantasy Points / Start","Fantasy Production","historical_points_per_start",modes=("Historical","Custom"),source="Finalized 2025/26 fantasy history"),
 _m("historical_ghost90","Ghost Points / 90","Ghost Floor","historical_ghost_per_90",modes=("Historical","Custom"),source="Finalized 2025/26 fantasy history"),
 _m("historical_ghoststart","Ghost Points / Start","Ghost Floor","historical_ghost_per_start",modes=("Historical","Custom"),source="Finalized 2025/26 fantasy history"),
 _m("historical_xgi90","xGI / 90","Attacking Output","historical_xgi_per_90",modes=("Historical","Custom"),digits=2,source="Understat 2025/26"),
 Metric("current_points","Current Fantasy Production","Current Season",{"Total":"current_fantasy_points","Per Game":"current_points_per_game","Per Start":"current_points_per_start","Per 90":"current_points_per_90"},modes=("Current Season","Custom"),source="2026/27 current_player_weekly"),
 Metric("current_ghost","Current Ghost Floor","Current Season",{"Total":"current_ghost_points","Per Game":"current_ghost_per_game","Per Start":"current_ghost_per_start","Per 90":"current_ghost_per_90"},modes=("Current Season","Custom"),source="2026/27 current_player_weekly"),
 Metric("current_xgi","Current xGI","Current Season",{"Total":"current_xgi","Per Game":"current_xgi_per_game","Per Start":"current_xgi_per_start","Per 90":"current_xgi_per_90"},digits=2,modes=("Current Season","Custom"),source="Understat 2026/27"),
 Metric("current_key_passes","Current Key Passes","Current Season",{"Total":"current_key_passes","Per Game":"current_key_passes_per_game","Per Start":"current_key_passes_per_start","Per 90":"current_key_passes_per_90"},modes=("Current Season","Custom"),source="2026/27 current_player_weekly"),
 Metric("current_tackles","Current Tackles Won","Current Season",{"Total":"current_tackles_won","Per Game":"current_tackles_won_per_game","Per Start":"current_tackles_won_per_start","Per 90":"current_tackles_won_per_90"},modes=("Current Season","Custom"),source="2026/27 current_player_weekly"),
 Metric("current_aerials","Current Aerials Won","Current Season",{"Total":"current_aerials_won","Per Game":"current_aerials_won_per_game","Per Start":"current_aerials_won_per_start","Per 90":"current_aerials_won_per_90"},modes=("Current Season","Custom"),source="2026/27 current_player_weekly"),
 _m("current_minutes","Current Minutes","Current Season","current_minutes",modes=("Current Season","Custom"),digits=0),
 _m("current_start_rate","Current Start Rate","Current Season","current_start_percentage",modes=("Current Season","Custom"),unit="percent"),
)}

PRESETS={
 "Balanced Profile":("projected_points","fantasy_production","ghost_floor","xgi","projected_minutes","fixture_ease"),
 "Projection":("projected_points","projected_minutes","minutes_confidence","club_strength","fixture_ease","draft_score"),
 "Historical Production":("fantasy_production","ghost_floor","xgi","start_rate","historical_minutes","historical_starts"),
 "Historical Balanced":("historical_fp90","historical_ghost90","historical_fpstart","start_rate","historical_xgi90","historical_season_points"),
 "Historical Floor & Minutes":("historical_ghost90","historical_ghoststart","historical_fpstart","start_rate","historical_minutes","historical_starts"),
 "Historical Attacking Upside":("historical_xgi90","xgi","historical_fp90","historical_season_points","historical_starts","start_rate"),
 "Floor and Minutes":("ghost_floor","fantasy_production","start_rate","historical_minutes","projected_minutes","minutes_confidence"),
 "Attacking Upside":("xgi","fantasy_production","projected_points","club_strength","fixture_ease","projected_minutes"),
 "Draft Value":("draft_score","projected_points","draft_value","projected_minutes","club_strength","fixture_ease"),
}
MODE_DEFAULTS={"Projection":PRESETS["Projection"],"Historical":PRESETS["Historical Production"],"Current Season":("current_points","current_ghost","current_xgi","current_minutes","current_start_rate","fixture_ease"),"Draft Profile":PRESETS["Draft Value"],"Custom":PRESETS["Balanced Profile"]}

def validate_metrics(keys,*,mode="Custom"):
    values=tuple(keys)
    if len(values)!=len(set(values)): raise ValueError("Duplicate radar metrics are not allowed.")
    if not 3<=len(values)<=8: raise ValueError("Choose between three and eight radar metrics.")
    unknown=set(values)-CATALOG.keys()
    if unknown: raise ValueError(f"Unsupported radar metrics: {sorted(unknown)}")
    invalid=[key for key in values if mode not in CATALOG[key].modes and mode!="Custom"]
    if invalid: raise ValueError(f"Metrics are not valid for {mode}: {invalid}")
    return values

def metrics_for_mode(mode): return tuple(key for key,m in CATALOG.items() if mode in m.modes or mode=="Custom")
