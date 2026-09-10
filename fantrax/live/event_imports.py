"""Local official CSV event imports; no network, scoring or state mutations.

Run: python -m fantrax.live.event_imports --transactions PATH --lineups PATH
Event IDs are content hashes, not Fantrax-issued transaction identifiers.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from config.project_paths import PROJECT_ROOT
from fantrax.live.current_identity import normalized_name
from fantrax.live.manager_identity import normalize_manager_alias

COMMON = ["Player", "Team", "Position", "Team.1", "Date (CDT)", "Gameweek"]
TYPES = {"Claim": "CLAIM", "Drop": "DROP", "Lineup Change": "LINEUP_CHANGE"}
STATES = {"Active": "ACTIVE", "Reserve": "RESERVE", "Inj Res": "INJURED_RESERVE"}


def digest(parts) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def clean(value) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


class IdentityBridge:
    """Unique exact normalized aliases only; ambiguous aliases never choose an ID."""
    def __init__(self, players: pd.DataFrame, teams: pd.DataFrame, history: pd.DataFrame):
        self.players = defaultdict(set)
        self.player_clubs = defaultdict(set)
        self.managers = defaultdict(set)
        team_ids = defaultdict(set)
        for row in teams.to_dict("records"):
            mid, tid = clean(row.get("manager_id")), clean(row.get("fantasy_team_id"))
            if mid and tid:team_ids[mid].add(tid)
            for field in ("manager_name", "fantasy_team_name"):
                alias = normalize_manager_alias(row.get(field))
                if alias and mid:self.managers[alias].add(mid)
        for row in history.to_dict("records"):
            alias, mid = normalize_manager_alias(row.get("display_name")), clean(row.get("manager_id"))
            if alias and mid:self.managers[alias].add(mid)
        self.team_ids = team_ids
        for row in players.to_dict("records"):
            pid = clean(row.get("fantrax_player_id"))
            if not pid:continue
            clubs = {clean(row.get(c)) for c in ("club", "premier_league_club", "current_team_code", "fantrax_current_team")} - {""}
            for field in ("player_name", "canonical_name", "fantrax_name", "fantrax_player_name"):
                alias = normalized_name(row.get(field))
                if not alias:continue
                self.players[alias].add(pid)
                for club in clubs:self.player_clubs[(alias, club)].add(pid)

    def resolve(self, player, club, manager):
        alias = normalized_name(player)
        candidates = self.players[alias]
        if len(candidates) > 1:candidates = self.player_clubs[(alias, clean(club))] or candidates
        managers = self.managers[normalize_manager_alias(manager)]
        def status(values):return "RESOLVED" if len(values)==1 else "AMBIGUOUS" if values else "UNRESOLVED"
        pid = next(iter(candidates)) if len(candidates)==1 else None
        mid = next(iter(managers)) if len(managers)==1 else None
        tids = self.team_ids[mid]
        return dict(player_id=pid, manager_id=mid, team_id=next(iter(tids)) if len(tids)==1 else None,
                    player_identity_status=status(candidates), manager_identity_status=status(managers),
                    identity_status="RESOLVED" if pid and mid and len(tids)==1 else "REVIEW")


def parse_timestamp(raw):
    try:
        parsed = datetime.strptime(raw, "%a %b %d, %Y, %I:%M%p")
        return pd.Timestamp(parsed).tz_localize("America/Chicago", ambiguous="raise", nonexistent="raise").isoformat()
    except (ValueError, TypeError):return None


def parse_bid(raw):
    if not raw:return None, None, "EMPTY"
    match = re.fullmatch(r"(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)", raw.strip())
    return (float(match[1]), float(match[2]), "PARSED_NEUTRAL") if match else (None, None, "UNPARSED")


def parse_slot(raw):
    parts = [part.strip() for part in raw.split(",")]
    state = STATES.get(parts[0])
    if state:
        slot = parts[1] if len(parts)==2 and parts[1] in {"G", "D", "M", "F"} else None
        valid = len(parts)==1 or slot is not None
        return state, slot, "PARSED" if valid else "PARTIAL"
    if len(parts)==1 and parts[0] in {"G", "D", "M", "F"}:return None, parts[0], "SLOT_ONLY"
    return None, None, "UNKNOWN"


def normalize(frame, kind, bridge, *, season="2627", league_id="o1wb36vdmrp1z5t8"):
    required = COMMON + (["Type", "Bid/Win", "Pr"] if kind=="transaction" else ["From", "To"])
    missing = set(required)-set(frame.columns)
    if missing:raise ValueError(f"{kind} export missing columns: {sorted(missing)}")
    occurrences = Counter();output = []
    for raw in frame.to_dict("records"):
        raw = {key: "" if pd.isna(value) else str(value) for key, value in raw.items()}
        fingerprint = digest([season, league_id, kind, raw])
        occurrences[fingerprint] += 1
        event_id = digest([fingerprint, occurrences[fingerprint]])
        timestamp = parse_timestamp(raw["Date (CDT)"])
        gw = int(raw["Gameweek"]) if re.fullmatch(r"[1-9]\d*", raw["Gameweek"]) else None
        identity = bridge.resolve(raw["Player"], raw["Team"], raw["Team.1"])
        errors = []
        if timestamp is None:errors.append("TIMESTAMP_PARSE_FAILURE")
        if gw is None:errors.append("INVALID_GAMEWEEK")
        if not raw["Player"].strip() or not raw["Team.1"].strip():errors.append("MISSING_NAME")
        row = dict(season_id=season, league_id=league_id, gameweek=gw, event_timestamp=timestamp,
                   raw_timestamp=raw["Date (CDT)"], raw_player_name=raw["Player"], raw_manager_name=raw["Team.1"],
                   club=raw["Team"], position=raw["Position"], **identity,
                   source=f"Fantrax official {kind} CSV export", raw_fields=json.dumps(raw, ensure_ascii=False, sort_keys=True))
        row[f"{kind}_event_id"] = event_id
        if kind=="transaction":
            typ = TYPES.get(raw["Type"], "UNKNOWN")
            first, second, bid_status = parse_bid(raw["Bid/Win"])
            priority = int(raw["Pr"]) if raw["Pr"].isdigit() else None
            if typ=="UNKNOWN":errors.append("UNKNOWN_TRANSACTION_TYPE")
            if bid_status=="UNPARSED":errors.append("BID_WIN_UNPARSED")
            if raw["Pr"] and priority is None:errors.append("PRIORITY_UNPARSED")
            # Same manager/minute is a candidate association, never an asserted API transaction ID.
            group = digest([season, league_id, identity["manager_id"] or raw["Team.1"], timestamp]) if timestamp and raw["Team.1"].strip() else None
            row.update(transaction_group_id=group, group_basis="MANAGER_EXACT_EXPORTED_TIMESTAMP" if group else None,
                       raw_transaction_type=raw["Type"], normalized_transaction_type=typ, player_action=typ,
                       raw_bid_win=raw["Bid/Win"], bid_component_1=first, bid_component_2=second,
                       bid_parse_status=bid_status, raw_priority=raw["Pr"], priority=priority)
        else:
            row.update(raw_from=raw["From"], raw_to=raw["To"])
            for side, field in (("from", "From"), ("to", "To")):
                state, slot, status = parse_slot(raw[field])
                row.update({f"{side}_roster_state":state, f"{side}_slot":slot, f"{side}_parse_status":status})
                if status in {"UNKNOWN", "PARTIAL"}:errors.append(f"{side.upper()}_UNPARSED")
        row["quality_flags"] = "|".join(errors)
        output.append(row)
    return pd.DataFrame(output)


def merge_events(existing, incoming, kind):
    """Preserve repeated identical rows within an export; deduplicate repeated imports."""
    key = f"{kind}_event_id"
    combined = pd.concat([existing, incoming], ignore_index=True)
    if combined.empty:return combined, 0
    result = combined.drop_duplicates(key, keep="last").reset_index(drop=True)
    return result, len(combined)-len(result)


def read_optional(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame()


def read_export(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        header = next(reader, [])
        for line, values in enumerate(reader, 2):
            if len(values) != len(header):raise ValueError(f"Malformed CSV row {line}: expected {len(header)} fields, got {len(values)}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if frame.empty:raise ValueError(f"Empty event export: {Path(path).name}; existing products retained")
    return frame


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def import_exports(transaction_path, lineup_path, *, root=PROJECT_ROOT, season="2627"):
    root = Path(root);model = root/"data"/"models"/f"season_{season}"
    players = pd.concat([read_optional(model/f"live_player_analytics_{season}.csv"),
                         read_optional(root/"data"/"reference"/f"player_registry_{season}.csv")], ignore_index=True)
    bridge = IdentityBridge(players, read_optional(model/f"league_teams_{season}.csv"), read_optional(model/f"manager_name_history_{season}.csv"))
    pending = [];report = {}
    for kind, path in (("transaction",transaction_path),("lineup",lineup_path)):
        # Structural CSV errors stop the import before either product is written.
        raw = read_export(path)
        events = normalize(raw, kind, bridge, season=season)
        output_path = model/f"{kind}_events_{season}.csv"
        merged, duplicates = merge_events(read_optional(output_path), events, kind)
        pending.append((output_path,merged))
        report[kind] = dict(rows_read=len(raw), events_normalized=len(events), total_events_stored=len(merged),
            duplicate_events_removed=duplicates, player_resolved=int(events.player_identity_status.eq("RESOLVED").sum()),
            player_unresolved=int(events.player_identity_status.ne("RESOLVED").sum()),
            manager_resolved=int(events.manager_identity_status.eq("RESOLVED").sum()),
            manager_unresolved=int(events.manager_identity_status.ne("RESOLVED").sum()),
            unique_players_resolved=int(events.player_id.nunique()), unique_managers_resolved=int(events.manager_id.nunique()),
            gameweeks=sorted(events.gameweek.dropna().astype(int).unique().tolist()),
            timestamp_parse_failures=int(events.event_timestamp.isna().sum()),
            quality_flags=events.quality_flags.value_counts().to_dict())
        if kind=="transaction":report[kind].update(transaction_groups=int(events.transaction_group_id.nunique()),
            raw_types=events.raw_transaction_type.value_counts().to_dict(), bid_parse_results=events.bid_parse_status.value_counts().to_dict())
    for path, frame in pending:atomic_write(path,frame.to_csv(index=False))
    atomic_write(root/"data"/"quality"/f"season_{season}"/f"event_import_quality_{season}.json",json.dumps(report,indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transactions", type=Path, required=True)
    parser.add_argument("--lineups", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(import_exports(args.transactions,args.lineups),indent=2))


if __name__=="__main__":main()
