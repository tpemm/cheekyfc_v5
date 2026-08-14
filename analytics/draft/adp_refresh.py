"""Read-only validation for a replacement Fantrax preseason export."""

from __future__ import annotations

from typing import Any

import pandas as pd


FIELD_ALIASES = {
    "player_id": ("ID", "api_player_id", "fantrax_player_id", "player_id"),
    "player": ("Player", "api_player_name", "fantrax_player_name", "player_name", "name"),
    "team": ("Team", "api_team_code", "team_code", "team", "team_short_name"),
    "position": ("Position", "api_position", "position", "positions"),
    "adp": ("ADP", "adp", "fantrax_adp", "average_draft_position", "avg_draft_position"),
    "projected_points": ("FPts", "fpts", "projected_points", "fantrax_projected_points"),
}


def _column(frame: pd.DataFrame, field: str) -> str | None:
    lookup = {str(column).casefold(): str(column) for column in frame.columns}
    return next((lookup[name.casefold()] for name in FIELD_ALIASES[field] if name.casefold() in lookup), None)


def validate_adp_export(frame: pd.DataFrame) -> dict[str, Any]:
    """Validate identity columns and ADP without rejecting legitimate blanks."""
    errors: list[str] = []
    warnings: list[str] = []
    columns = {field: _column(frame, field) for field in FIELD_ALIASES}
    for field in ("player_id", "player", "team", "position", "adp"):
        if columns[field] is None:
            errors.append(f"Missing required {field} column; accepted names: {', '.join(FIELD_ALIASES[field])}")
    if frame.empty:
        errors.append("Fantrax export is empty")
    if errors:
        return {"valid": False, "rows": len(frame), "columns": columns, "errors": errors, "warnings": warnings, "malformed_adp": 0, "missing_adp": 0, "duplicate_ids": 0}

    ids = frame[columns["player_id"]].fillna("").astype(str).str.strip().str.strip("*")
    missing_ids = int(ids.eq("").sum())
    if missing_ids:
        errors.append(f"{missing_ids} rows have missing player IDs")
    duplicate_ids = int(ids[ids.ne("")].duplicated(keep=False).sum())
    if duplicate_ids:
        warnings.append(f"{duplicate_ids} rows have duplicate Fantrax IDs")
    raw_adp = frame[columns["adp"]]
    numeric_adp = pd.to_numeric(raw_adp, errors="coerce")
    normalized_adp = raw_adp.astype(str).str.strip().str.casefold()
    missing_tokens = {"", "-", "--", "n/a", "na", "nan", "none"}
    supplied = raw_adp.notna() & ~normalized_adp.isin(missing_tokens)
    malformed = int((supplied & numeric_adp.isna()).sum())
    missing = int((~supplied).sum())
    if malformed:
        errors.append(f"{malformed} supplied ADP values are not numeric")
    if missing:
        warnings.append(f"{missing} players have missing ADP; missing ADP is allowed")
    if len(frame) < 100:
        warnings.append(f"Row count {len(frame)} is unusually low for a Premier League player pool")
    if columns["projected_points"] == columns["adp"]:
        errors.append("ADP and projected points resolve to the same column")
    return {
        "valid": not errors,
        "rows": len(frame),
        "columns": columns,
        "errors": errors,
        "warnings": warnings,
        "malformed_adp": malformed,
        "missing_adp": missing,
        "duplicate_ids": duplicate_ids,
        "adp_numeric": int(numeric_adp.notna().sum()),
    }
