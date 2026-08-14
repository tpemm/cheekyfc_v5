"""Build the canonical player registry from cached source datasets."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.current_squads.cache import read_snapshot
from analytics.draft.reliability import normalize_player_id, normalize_team, normalize_text
from analytics.player_registry.matcher import match_current_players

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def registry_id(*values: object) -> str:
    material = "|".join(str(value).strip().casefold() for value in values if str(value).strip())
    return "pr_" + hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]


def _latest_nonempty(values: pd.Series) -> object:
    usable = values[values.notna() & values.astype(str).str.strip().ne("")]
    return usable.iloc[-1] if not usable.empty else pd.NA


def build_historical(master: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "historical_player_id": master["fantrax_player_id"].map(normalize_player_id),
            "historical_name": master.get("fantrax_player_name", "").replace("", pd.NA),
            "historical_team": master.get("avail_team", master.get("mgr_team", "")).map(normalize_team),
            "historical_position": master.get("avail_position", "").astype(str),
            "gw": pd.to_numeric(master.get("fantrax_gw"), errors="coerce"),
            "historical_minutes": pd.to_numeric(master.get("mgr_min"), errors="coerce"),
            "historical_starts": pd.to_numeric(master.get("mgr_gs"), errors="coerce"),
            "historical_points": pd.to_numeric(master.get("official_fantasy_points"), errors="coerce"),
            "understat_player_id": master.get("understat_player_id", "").replace("", pd.NA),
        }
    )
    frame = frame.sort_values(["historical_player_id", "gw"]).drop_duplicates(
        ["historical_player_id", "gw"], keep="last"
    )
    return frame.groupby("historical_player_id", as_index=False).agg(
        historical_name=("historical_name", _latest_nonempty),
        historical_team=("historical_team", _latest_nonempty),
        historical_position=("historical_position", _latest_nonempty),
        historical_minutes=("historical_minutes", "sum"),
        historical_starts=("historical_starts", "sum"),
        historical_points=("historical_points", "sum"),
        understat_player_id=("understat_player_id", _latest_nonempty),
    )


def build_player_registry(
    fantrax: pd.DataFrame,
    current: pd.DataFrame,
    historical: pd.DataFrame,
    bridge: pd.DataFrame | None = None,
    overrides: pd.DataFrame | None = None,
    alias_overrides: pd.DataFrame | None = None,
    *,
    season_id: str = "2627",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return registry, quality report, and unresolved report."""
    fantrax = fantrax.copy()
    current = current.copy()
    current["team_code"] = current["team_code"].map(normalize_team)
    historical = historical.copy()
    historical["historical_player_id"] = historical["historical_player_id"].map(
        normalize_player_id
    )
    fantrax["fantrax_player_id"] = fantrax["fantrax_player_id"].map(normalize_player_id)
    fantrax = fantrax.drop_duplicates("fantrax_player_id", keep="last")
    decisions = match_current_players(
        fantrax, current, overrides, alias_overrides
    )
    registry = fantrax.merge(decisions, on="fantrax_player_id", how="left")

    registry["historical_player_id"] = registry["fantrax_player_id"]
    if bridge is not None and not bridge.empty:
        bridge_keep = pd.DataFrame(
            {
                "fantrax_player_id": bridge["api_player_id"].map(normalize_player_id),
                "bridged_historical_id": bridge["fantrax_player_id"].map(normalize_player_id),
            }
        ).drop_duplicates("fantrax_player_id", keep="last")
        registry = registry.merge(bridge_keep, on="fantrax_player_id", how="left")
        registry["historical_player_id"] = registry["bridged_historical_id"].fillna(
            registry["historical_player_id"]
        )
        registry = registry.drop(columns="bridged_historical_id")
    registry = registry.merge(historical, on="historical_player_id", how="left")

    current_keep = current.rename(
        columns={
            "provider_player_id": "fpl_player_id",
            "player_name": "current_fpl_name",
            "team_name": "current_team",
            "team_code": "current_team_code",
            "position": "current_position",
            "provider": "current_source",
            "retrieved_at": "last_verified",
        }
    )
    registry = registry.merge(
        current_keep[
            [
                "fpl_player_id", "current_fpl_name", "current_team",
                "current_team_code", "current_position", "active_epl",
                "availability_status", "injury_news", "current_source", "last_verified",
            ]
        ],
        on="fpl_player_id",
        how="left",
    )
    has_current = registry["fpl_player_id"].fillna("").ne("")
    has_history = registry["historical_name"].notna() | registry["historical_minutes"].notna()
    transferred = has_current & has_history & registry["historical_team"].ne(
        registry["current_team_code"]
    )
    registry["registry_status"] = np.select(
        [transferred, has_current & ~has_history, has_current, has_history],
        ["Transferred", "New EPL Arrival", "Confirmed", "Historical Only"],
        default="Unresolved",
    )
    registry["source"] = np.where(
        has_current,
        registry["current_source"],
        "Fantrax / historical",
    )
    registry["fantrax_name"] = registry["player_name"]
    registry["fpl_name"] = registry["current_fpl_name"].combine_first(registry["fpl_name"])
    registry["canonical_name"] = (
        registry["fpl_name"].replace("", pd.NA).combine_first(registry["fantrax_name"])
    )
    registry["normalized_name"] = registry["canonical_name"].map(normalize_text)
    registry["current_team"] = registry["current_team"].combine_first(
        registry["team_2627"]
    )
    registry["current_team_code"] = registry["current_team_code"].combine_first(
        registry["team_2627"].map(normalize_team)
    )
    registry["current_position"] = registry["current_position"].combine_first(
        registry["position_2627"]
    )
    registry["active_epl"] = registry["active_epl"].fillna(False).astype(bool)
    registry["availability_status"] = registry["availability_status"].fillna("unverified")
    registry["injury_news"] = registry["injury_news"].fillna("")
    registry["last_verified"] = registry["last_verified"].fillna("")
    registry["registry_player_id"] = [
        registry_id(fpl_id, fantrax_id, historical_id, name)
        for fpl_id, fantrax_id, historical_id, name in zip(
            registry["fpl_player_id"],
            registry["fantrax_player_id"],
            registry["historical_player_id"],
            registry["canonical_name"],
        )
    ]
    registry["season_id"] = season_id

    columns = [
        "registry_player_id", "fantrax_player_id", "fpl_player_id",
        "understat_player_id", "historical_player_id", "canonical_name",
        "fantrax_name", "fpl_name", "historical_name", "normalized_name",
        "current_team", "current_team_code", "current_position", "active_epl",
        "availability_status", "injury_news", "historical_team",
        "historical_position", "historical_minutes", "historical_starts",
        "historical_points", "registry_status", "match_method",
        "identity_confidence", "alias_source", "source", "last_verified", "match_diagnostic",
        "season_id",
    ]
    registry = registry[columns]

    matched_fpl_ids = set(registry["fpl_player_id"].fillna("").astype(str))
    fpl_only_rows = []
    for _, player in current[
        ~current["provider_player_id"].astype(str).isin(matched_fpl_ids)
    ].iterrows():
        fpl_id = str(player["provider_player_id"])
        name = str(player["player_name"])
        fpl_only_rows.append(
            {
                "registry_player_id": registry_id(fpl_id, name),
                "fantrax_player_id": "",
                "fpl_player_id": fpl_id,
                "understat_player_id": pd.NA,
                "historical_player_id": "",
                "canonical_name": name,
                "fantrax_name": "",
                "fpl_name": name,
                "historical_name": pd.NA,
                "normalized_name": normalize_text(name),
                "current_team": player["team_name"],
                "current_team_code": player["team_code"],
                "current_position": player["position"],
                "active_epl": True,
                "availability_status": player["availability_status"],
                "injury_news": player["injury_news"],
                "historical_team": pd.NA,
                "historical_position": pd.NA,
                "historical_minutes": pd.NA,
                "historical_starts": pd.NA,
                "historical_points": pd.NA,
                "registry_status": "Confirmed",
                "match_method": "FPL ID",
                "identity_confidence": 97,
                "alias_source": "",
                "source": player["provider"],
                "last_verified": player["retrieved_at"],
                "match_diagnostic": "Active FPL player absent from Fantrax export",
                "season_id": season_id,
            }
        )
    if fpl_only_rows:
        registry = pd.concat(
            [registry, pd.DataFrame(fpl_only_rows, columns=columns)],
            ignore_index=True,
        )

    registry = registry.sort_values(
        ["active_epl", "canonical_name", "registry_player_id"],
        ascending=[False, True, True],
    ).reset_index(drop=True)
    if registry["registry_player_id"].duplicated().any():
        raise ValueError("Duplicate registry_player_id values")
    active_duplicates = registry.loc[
        registry["active_epl"],
        ["fpl_player_id", "fantrax_player_id"],
    ].duplicated().any()
    if active_duplicates:
        raise ValueError("Duplicate active player identities")

    quality_rows = [
            {"metric": "registry_rows", "value": len(registry)},
            {"metric": "active_epl", "value": int(registry["active_epl"].sum())},
            {"metric": "fantrax_linked", "value": int(registry["fantrax_player_id"].ne("").sum())},
            {"metric": "fpl_linked", "value": int(registry["fpl_player_id"].fillna("").ne("").sum())},
            {"metric": "historical_linked", "value": int(registry["historical_name"].notna().sum())},
            {"metric": "unresolved", "value": int(registry["registry_status"].eq("Unresolved").sum())},
            {"metric": "transferred", "value": int(registry["registry_status"].eq("Transferred").sum())},
            {"metric": "built_in_aliases", "value": int(registry["alias_source"].eq("Built-in Alias").sum())},
            {"metric": "user_approved_aliases", "value": int(registry["alias_source"].eq("User-Approved Alias").sum())},
            {"metric": "duplicate_registry_ids", "value": int(registry["registry_player_id"].duplicated().sum())},
            {"metric": "duplicate_active_fpl_ids", "value": int(registry.loc[registry["active_epl"], "fpl_player_id"].duplicated().sum())},
    ]
    for status, count in registry["registry_status"].value_counts().sort_index().items():
        quality_rows.append({"metric": f"status_{normalize_text(status).replace(' ', '_')}", "value": int(count)})
    for method, count in registry["match_method"].value_counts().sort_index().items():
        quality_rows.append({"metric": f"method_{normalize_text(method).replace(' ', '_')}", "value": int(count)})
    for confidence, count in registry["identity_confidence"].value_counts().sort_index().items():
        quality_rows.append({"metric": f"confidence_{int(confidence)}", "value": int(count)})
    promoted_codes = {"COV", "HUL", "IPS"}
    quality_rows.extend(
        [
            {
                "metric": "promoted_clubs_represented",
                "value": int(
                    len(
                        promoted_codes
                        & set(registry.loc[registry["active_epl"], "current_team_code"])
                    )
                ),
            },
            {
                "metric": "active_players_promoted_clubs",
                "value": int(
                    registry.loc[registry["active_epl"], "current_team_code"]
                    .isin(promoted_codes)
                    .sum()
                ),
            },
        ]
    )
    quality = pd.DataFrame(quality_rows)
    unresolved = registry[
        registry["registry_status"].eq("Unresolved")
        | registry["match_method"].eq("Unresolved")
    ].copy()
    return registry, quality, unresolved


def build_from_cache(season_id: str = "2627") -> Path:
    reference = PROJECT_ROOT / "data" / "reference"
    current = read_snapshot(
        reference / "current_squads" / f"fpl_players_{season_id}.csv"
    )
    from scripts.build_draft_tool_v1_2_2_2627 import load_current_fantrax

    fantrax = load_current_fantrax(
        PROJECT_ROOT / "data" / "imports" / "draft" / "Fantrax-Players-Cheeky FC (7).csv"
    )
    master = pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "master_player_weekly_2526.csv",
        low_memory=False,
    )
    historical = build_historical(master)
    bridge_path = reference / "api_to_master_player_id_bridge_2526.csv"
    bridge = pd.read_csv(bridge_path) if bridge_path.exists() else pd.DataFrame()
    alias_path = (
        reference / "player_registry" / f"player_alias_overrides_{season_id}.csv"
    )
    alias_overrides = (
        pd.read_csv(alias_path, dtype=str, keep_default_na=False)
        if alias_path.exists()
        else pd.DataFrame()
    )
    registry, quality, unresolved = build_player_registry(
        fantrax, current, historical, bridge, alias_overrides=alias_overrides,
        season_id=season_id
    )
    review_path = (
        reference / "player_registry" / f"player_identity_review_{season_id}.csv"
    )
    if review_path.exists():
        review = pd.read_csv(review_path, low_memory=False)
        review_metrics = pd.DataFrame(
            [
                {
                    "metric": "unresolved_high_confidence_candidates",
                    "value": int(
                        review.get("confidence_class", pd.Series(dtype=str))
                        .eq("High confidence")
                        .sum()
                    ),
                },
                {
                    "metric": "ignored_candidates",
                    "value": int(
                        review.get("review_status", pd.Series(dtype=str))
                        .eq("Ignored")
                        .sum()
                    ),
                },
                {
                    "metric": "unreviewed_candidates",
                    "value": int(
                        review.get("review_status", pd.Series(dtype=str))
                        .eq("Unreviewed")
                        .sum()
                    ),
                },
            ]
        )
        quality = pd.concat([quality, review_metrics], ignore_index=True)
    registry_path = reference / f"player_registry_{season_id}.csv"
    registry.to_csv(registry_path, index=False, encoding="utf-8-sig")
    quality_dir = PROJECT_ROOT / "data" / "quality" / f"player_registry_{season_id}"
    quality_dir.mkdir(parents=True, exist_ok=True)
    quality.to_csv(quality_dir / "player_registry_quality_report.csv", index=False)
    unresolved.to_csv(quality_dir / "player_registry_unresolved.csv", index=False, encoding="utf-8-sig")
    return registry_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season-id", default="2627")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    path = build_from_cache(args.season_id)
    registry = pd.read_csv(path, low_memory=False)
    print(f"Player registry: {len(registry)} rows at {path}")
    if args.validate_only:
        print("Registry validation passed.")


if __name__ == "__main__":
    main()
