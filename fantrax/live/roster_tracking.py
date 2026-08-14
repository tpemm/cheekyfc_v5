"""Deterministic current-roster snapshots, change events, history, and ownership."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


EVENT_COLUMNS = (
    "event_id", "season_id", "detected_at", "effective_period", "event_type",
    "fantrax_player_id", "registry_player_id", "player_name",
    "previous_manager_id", "previous_manager_name", "new_manager_id", "new_manager_name",
    "previous_roster_status", "new_roster_status", "previous_lineup_status", "new_lineup_status",
    "previous_snapshot_checksum", "new_snapshot_checksum", "authoritative_transaction_id",
    "transaction_confirmation_status", "source", "note",
)

HISTORY_COLUMNS = (
    "season_id", "fantrax_player_id", "registry_player_id", "player_name", "manager_id", "manager_name",
    "fantasy_team_id", "fantasy_team_name", "ownership_started_at", "ownership_ended_at", "start_period",
    "end_period", "roster_status", "lineup_status", "acquisition_event_id", "departure_event_id",
    "currently_active", "source",
)

VOLATILE_COLUMNS = {"observed_at", "source_retrieved_at", "last_refreshed", "validation_status"}


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def stable_roster_checksum(frame: pd.DataFrame) -> str:
    stable = frame.drop(columns=[column for column in VOLATILE_COLUMNS if column in frame], errors="ignore").copy()
    stable = stable.reindex(sorted(stable.columns), axis=1).fillna("")
    keys = [column for column in ("fantrax_player_id", "manager_id", "lineup_status", "roster_status") if column in stable]
    if keys:
        stable = stable.sort_values(keys, kind="stable")
    encoded = stable.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _value(row: dict[str, Any] | None, key: str) -> Any:
    if not row:
        return None
    value = row.get(key)
    return None if pd.isna(value) else value


def _lineup_event(previous: dict[str, Any], current: dict[str, Any]) -> str | None:
    before = str(_value(previous, "lineup_status") or "").lower()
    after = str(_value(current, "lineup_status") or "").lower()
    if before == after:
        return None
    ir = {"ir", "injured reserve", "injured_reserve"}
    reserve = {"reserve", "bench", "res"}
    active = {"active", "starter", "starting"}
    if after in ir: return "MOVED_TO_IR"
    if before in ir and after not in ir: return "RETURNED_FROM_IR"
    if after in reserve: return "MOVED_TO_RESERVE"
    if after in active: return "MOVED_TO_ACTIVE"
    return "LINEUP_POSITION_CHANGED"


def detect_changes(previous: pd.DataFrame, current: pd.DataFrame, *, previous_checksum: str, new_checksum: str, detected_at: str, period: int) -> pd.DataFrame:
    """Compare two distinct snapshots; IDs are stable across repeated builds."""
    before = {str(row["fantrax_player_id"]): row for row in previous.to_dict("records")}
    after = {str(row["fantrax_player_id"]): row for row in current.to_dict("records")}
    events: list[dict[str, Any]] = []
    for player_id in sorted(set(before) | set(after)):
        old, new = before.get(player_id), after.get(player_id)
        types: list[str] = []
        if old is None: types = ["PLAYER_ADDED"]
        elif new is None: types = ["PLAYER_DROPPED"]
        elif _value(old, "manager_id") != _value(new, "manager_id"): types = ["PLAYER_TRANSFERRED_BETWEEN_MANAGERS"]
        else:
            lineup = _lineup_event(old, new)
            if lineup: types.append(lineup)
            if _value(old, "registry_player_id") != _value(new, "registry_player_id"):
                types.append("PLAYER_IDENTITY_RESOLVED" if not _value(old, "registry_player_id") else "PLAYER_IDENTITY_CHANGED")
            if _value(old, "roster_status") != _value(new, "roster_status") and not lineup:
                types.append("UNKNOWN_CHANGE")
        for event_type in types:
            identity = "|".join((previous_checksum, new_checksum, player_id, event_type))
            event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            row = new or old or {}
            events.append({
                "event_id": event_id, "season_id": _value(row, "season_id"), "detected_at": detected_at,
                "effective_period": period, "event_type": event_type, "fantrax_player_id": player_id,
                "registry_player_id": _value(new, "registry_player_id") or _value(old, "registry_player_id"),
                "player_name": _value(new, "player_name") or _value(old, "player_name"),
                "previous_manager_id": _value(old, "manager_id"), "previous_manager_name": _value(old, "manager_name"),
                "new_manager_id": _value(new, "manager_id"), "new_manager_name": _value(new, "manager_name"),
                "previous_roster_status": _value(old, "roster_status"), "new_roster_status": _value(new, "roster_status"),
                "previous_lineup_status": _value(old, "lineup_status"), "new_lineup_status": _value(new, "lineup_status"),
                "previous_snapshot_checksum": previous_checksum, "new_snapshot_checksum": new_checksum,
                "authoritative_transaction_id": pd.NA, "transaction_confirmation_status": "unconfirmed",
                "source": "Fantrax roster snapshot comparison", "note": "Manager movement is not classified as a trade without confirmation.",
            })
    return pd.DataFrame(events, columns=EVENT_COLUMNS)


def update_history(existing: pd.DataFrame, current: pd.DataFrame, events: pd.DataFrame, *, observed_at: str, period: int) -> pd.DataFrame:
    history = existing.reindex(columns=HISTORY_COLUMNS).copy() if not existing.empty else pd.DataFrame(columns=HISTORY_COLUMNS)
    if history.empty:
        rows = []
        for row in current.to_dict("records"):
            rows.append({**{column: pd.NA for column in HISTORY_COLUMNS}, **{column: row.get(column) for column in HISTORY_COLUMNS if column in row},
                "ownership_started_at": observed_at, "start_period": period, "currently_active": True, "source": "Fantrax roster baseline"})
        return pd.DataFrame(rows, columns=HISTORY_COLUMNS)
    if events.empty:
        return history
    current_by_id = {str(row["fantrax_player_id"]): row for row in current.to_dict("records")}
    for event in events.drop_duplicates("fantrax_player_id", keep="first").to_dict("records"):
        player_id = str(event["fantrax_player_id"])
        active = history["fantrax_player_id"].astype(str).eq(player_id) & history["currently_active"].fillna(False).astype(bool)
        if active.any():
            history.loc[active, ["ownership_ended_at", "end_period", "departure_event_id", "currently_active"]] = [observed_at, period, event["event_id"], False]
        row = current_by_id.get(player_id)
        if row is not None:
            addition = {column: row.get(column, pd.NA) for column in HISTORY_COLUMNS}
            addition.update({"ownership_started_at": observed_at, "start_period": period, "acquisition_event_id": event["event_id"], "currently_active": True, "source": "Fantrax roster change"})
            history = pd.concat([history, pd.DataFrame([addition], columns=HISTORY_COLUMNS)], ignore_index=True)
    return history.drop_duplicates()


def archive_snapshot(current: pd.DataFrame, *, archive_root: Path, season_id: str, league_id: str | None, observed_at: str, source_retrieved_at: str, period: int, valid: bool) -> dict[str, Any]:
    checksum = stable_roster_checksum(current)
    metadata_files = sorted(archive_root.glob("*.metadata.json")) if archive_root.exists() else []
    previous = json.loads(metadata_files[-1].read_text(encoding="utf-8")) if metadata_files else None
    if previous and previous.get("checksum") == checksum:
        return {**previous, "materially_changed": False, "created": False}
    if not valid:
        return {"checksum": checksum, "materially_changed": bool(previous), "created": False, "validation_result": "invalid"}
    stamp = pd.Timestamp(observed_at).strftime("%Y%m%d_%H%M%S_%f")
    path = archive_root / f"rosters_{season_id}_{stamp}.csv"
    metadata = {"season_id": season_id, "league_id": league_id, "observed_at": observed_at, "source_retrieved_at": source_retrieved_at,
        "scoring_period": period, "row_count": len(current), "manager_count": int(current["manager_id"].nunique()), "checksum": checksum,
        "validation_result": "valid", "previous_snapshot_checksum": previous.get("checksum") if previous else None,
        "materially_changed": previous is not None, "created": True, "snapshot_path": str(path)}
    atomic_csv(current, path); atomic_json(metadata, path.with_suffix(".metadata.json"))
    return metadata
