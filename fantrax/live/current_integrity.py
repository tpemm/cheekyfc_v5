"""Cache-first current-season integrity and Fantrax correction utilities."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


IDENTITY_COLUMNS = ("ID", "Player", "Team", "Eligible", "Status", "Opponent")


def read_fantrax_snapshot(path: Path) -> pd.DataFrame:
    """Read and combine a timestamped snapshot without mutating it."""
    parts = []
    for csv_path in sorted(path.glob("team_*.csv")):
        frame = pd.read_csv(csv_path, skiprows=1)
        frame["manager_id"] = csv_path.stem.removeprefix("team_")
        parts.append(frame)
    if not parts:
        csv_path = path / "all_players.csv"
        if csv_path.exists():
            parts.append(pd.read_csv(csv_path))
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True, sort=False)
    if "ID" in frame:
        frame["fantrax_player_id"] = frame["ID"].astype("string").str.strip("*")
    return frame


def correction_diff(previous: pd.DataFrame, current: pd.DataFrame, *, previous_snapshot: str, new_snapshot: str, period: int) -> pd.DataFrame:
    """Long-form numeric diff across every shared detailed Fantrax field."""
    columns = ("period", "fantrax_player_id", "player_name", "manager_id", "roster_status",
               "metric", "old_value", "new_value", "delta", "previous_snapshot", "new_snapshot")
    if previous.empty or current.empty:
        return pd.DataFrame(columns=columns)
    key = "fantrax_player_id"
    shared = [c for c in previous.columns if c in current and c not in IDENTITY_COLUMNS and c not in (key, "manager_id")]
    numeric = [c for c in shared if pd.to_numeric(previous[c], errors="coerce").notna().any() or pd.to_numeric(current[c], errors="coerce").notna().any()]
    old = previous.drop_duplicates(key, keep="last").set_index(key)
    new = current.drop_duplicates(key, keep="last").set_index(key)
    rows = []
    for pid in old.index.intersection(new.index):
        for metric in numeric:
            a = pd.to_numeric(pd.Series([old.at[pid, metric]]), errors="coerce").iat[0]
            b = pd.to_numeric(pd.Series([new.at[pid, metric]]), errors="coerce").iat[0]
            if (pd.isna(a) and pd.isna(b)) or (pd.notna(a) and pd.notna(b) and float(a) == float(b)):
                continue
            rows.append({"period": period, "fantrax_player_id": pid,
                         "player_name": new.at[pid, "Player"] if "Player" in new else pd.NA,
                         "manager_id": new.at[pid, "manager_id"] if "manager_id" in new else pd.NA,
                         "roster_status": new.at[pid, "Status"] if "Status" in new else pd.NA,
                         "metric": metric, "old_value": a, "new_value": b,
                         "delta": b-a if pd.notna(a) and pd.notna(b) else pd.NA,
                         "previous_snapshot": previous_snapshot, "new_snapshot": new_snapshot})
    return pd.DataFrame(rows, columns=columns)


def reconcile_snapshot_directory(snapshot_root: Path, period: int) -> tuple[pd.DataFrame, dict]:
    snapshots = sorted(p for p in snapshot_root.iterdir() if p.is_dir()) if snapshot_root.exists() else []
    if len(snapshots) < 2:
        diff = correction_diff(pd.DataFrame(), pd.DataFrame(), previous_snapshot="", new_snapshot="", period=period)
    else:
        diff = correction_diff(read_fantrax_snapshot(snapshots[-2]), read_fantrax_snapshot(snapshots[-1]),
                               previous_snapshot=snapshots[-2].name, new_snapshot=snapshots[-1].name, period=period)
    summary = {"period": period, "snapshot_count": len(snapshots),
               "previous_snapshot": snapshots[-2].name if len(snapshots) > 1 else None,
               "new_snapshot": snapshots[-1].name if snapshots else None,
               "players_changed": int(diff.fantrax_player_id.nunique()) if len(diff) else 0,
               "stat_fields_changed": int(diff.metric.nunique()) if len(diff) else 0,
               "managers_affected": int(diff.manager_id.nunique()) if len(diff) else 0,
               "period_state": "COMPLETE_PENDING_CORRECTIONS"}
    return diff, summary


def metric_validation(fantrax: pd.DataFrame, advanced: pd.DataFrame) -> pd.DataFrame:
    """Empirical overlap statistics plus conservative semantic classification."""
    specs = [
        ("goals", "goals", "goals", "SAFE_SUPPLEMENT", True, "Same scoring event semantics."),
        ("fantasy_assists", "assists", "assists", "SOURCE_SPECIFIC", False, "Fantrax fantasy assists are not official assists."),
        ("key_passes", "key_passes", "key_passes", "SAFE_SUPPLEMENT", True, "Historically and currently close event semantics."),
        ("shots_on_target", "shots_on_target", "shots_on_target", "SOURCE_SPECIFIC", False, "Provider shot-on-target definitions differ."),
        ("tackles_won", "tackles_won", "tackles", "SOURCE_SPECIFIC", False, "Won tackles are not raw tackles."),
        ("interceptions", "interceptions", "interceptions", "SAFE_SUPPLEMENT", True, "Equivalent event family."),
        ("clearances", "clearances", "clearances", "CAVEAT_SUPPLEMENT", False, "Known provider event-definition variance."),
        ("aerial_wins", "aerials_won", "aerial_wins", "SAFE_SUPPLEMENT", True, "Equivalent won-aerial event."),
        ("crosses", "accurate_crosses", "raw_crosses", "DO_NOT_SUPPLEMENT", False, "Accurate crosses are not raw crosses."),
    ]
    if fantrax.empty or advanced.empty:
        joined = pd.DataFrame()
    else:
        left = fantrax[fantrax.get("current_manager_id", pd.Series(index=fantrax.index)).notna()].copy()
        right = advanced.copy()
        left["fantrax_player_id"] = left.fantrax_player_id.astype(str)
        right["fantrax_player_id"] = right.fantrax_player_id.astype(str)
        right["period"] = pd.to_numeric(right.get("fantrax_period"), errors="coerce")
        joined = left.merge(right, on=["fantrax_player_id", "period"], suffixes=("_fantrax", "_whoscored"))
    rows=[]
    for metric, ff, wf, classification, approved, note in specs:
        fcol = ff+"_fantrax" if ff+"_fantrax" in joined else ff
        wcol = wf+"_whoscored" if wf+"_whoscored" in joined else wf
        a=pd.to_numeric(joined.get(fcol,pd.Series(dtype=float)),errors="coerce");b=pd.to_numeric(joined.get(wcol,pd.Series(dtype=float)),errors="coerce")
        valid=a.notna()&b.notna();delta=(b[valid]-a[valid]);n=int(valid.sum())
        rows.append({"metric":metric,"fantrax_field":ff,"whoscored_field":wf,"sample_rows":n,
                     "exact_matches":int(delta.eq(0).sum()),"exact_rate":float(delta.eq(0).mean()) if n else pd.NA,
                     "mean_difference":float(delta.mean()) if n else pd.NA,"mean_absolute_difference":float(delta.abs().mean()) if n else pd.NA,
                     "zero_agreement_rate":float(((a[valid]==0)&(b[valid]==0)).sum()/max(1,((a[valid]==0)|(b[valid]==0)).sum())) if n else pd.NA,
                     "semantic_note":note,"historical_2526_evidence":"See fantrax_supplemental_stat_policy_2526.csv",
                     "gw1_2627_evidence":f"{n} exact identity/player-period rows","classification":classification,
                     "approved_for_waiver_supplement":approved,"reason":note})
    return pd.DataFrame(rows)
