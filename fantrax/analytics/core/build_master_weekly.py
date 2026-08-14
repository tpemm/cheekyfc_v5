from __future__ import annotations

import sys

import re
import csv
from pathlib import Path

import pandas as pd


# =========================
# CONFIG
# =========================
# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT

SEASON_STR = "2025/26"
SEASON_ID = "2526"  # used only in output naming

FANTRAX_ALL_PLAYERS_DIR = PROJECT_ROOT / "data" / "raw" / "fantrax" / "all_players_weekly"
FANTRAX_TEAM_ROSTERS_DIR = PROJECT_ROOT / "data" / "raw" / "fantrax" / "team_rosters_weekly"

UNDERSTAT_DIR = PROJECT_ROOT / "data" / "raw" / "understat"
UNDERSTAT_PMS_CSV = UNDERSTAT_DIR / f"understat_player_match_stats_{SEASON_ID}_ENG-Premier_League.csv"

REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
CROSSWALK_PATH = REFERENCE_DIR / "understat_fantrax_player_id_map.csv"
SCORING_PERIODS_PATH = REFERENCE_DIR / f"fantrax_scoring_periods_{SEASON_ID}.csv"

OUT_DIR = PROJECT_ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_FANTRAX_AVAILABLE = OUT_DIR / f"fantrax_available_weekly_all_{SEASON_ID}.csv"
OUT_FANTRAX_ROSTERED = OUT_DIR / f"fantrax_rostered_weekly_all_{SEASON_ID}.csv"
OUT_UNDERSTAT_WEEKLY = OUT_DIR / f"understat_weekly_by_fantrax_gw_{SEASON_ID}.csv"
OUT_UNDERSTAT_MATCH_MAP = OUT_DIR / f"understat_match_to_fantrax_gw_{SEASON_ID}.csv"
OUT_MASTER = OUT_DIR / f"master_player_weekly_{SEASON_ID}.csv"
OUT_UNMAPPED_FANTRAX = OUT_DIR / f"unmapped_fantrax_players_{SEASON_ID}.csv"
OUT_UNMAPPED_UNDERSTAT = OUT_DIR / f"unmapped_understat_players_{SEASON_ID}.csv"
OUT_CROSSWALK_DUPES = OUT_DIR / f"crosswalk_duplicates_fantrax_{SEASON_ID}.csv"

# If True, fill missing Understat numeric stats with 0 after merge into master
FILL_UNDERSTAT_NA_WITH_ZERO = False


# =========================
# Helpers
# =========================
def norm_col(c: str) -> str:
    c = str(c).strip()
    if c == "+/-":
        return "plus_minus"
    c = c.replace("FP/G", "FP_per_G")
    c = c.replace(" ", "_").replace("/", "_per_")
    c = re.sub(r"[^A-Za-z0-9_]+", "", c)
    return c.lower()


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s


def coerce_numeric_cols(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def coerce_id_str(df: pd.DataFrame, col: str) -> None:
    """Coerce an ID column to clean string for consistent merges."""
    if col not in df.columns:
        return
    s = df[col].astype(str).str.strip()
    s = s.replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})
    df[col] = s


def _safe_read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8", engine="python")


# =========================
# Fantrax: Available Players weekly (everyone)
# =========================
def parse_available_weekly(path: Path) -> pd.DataFrame:
    m = re.search(r"AvailablePlayers_GW(\d+)\.csv$", path.name, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse GW from filename: {path.name}")
    gw = int(m.group(1))

    df = _safe_read_csv(path)

    if "ID" not in df.columns:
        raise ValueError(f"{path.name}: missing ID column. Columns={list(df.columns)}")

    df = df.rename(columns={"ID": "fantrax_player_id"})
    coerce_id_str(df, "fantrax_player_id")

    df["season"] = SEASON_STR
    df["fantrax_gw"] = gw

    # Drop totally blank trailing column if it exists (often "Column1")
    blank_cols = [c for c in df.columns if c.lower().startswith("column") and df[c].isna().all()]
    if blank_cols:
        df = df.drop(columns=blank_cols)

    keep_keys = {"fantrax_player_id", "season", "fantrax_gw"}
    df.columns = [c if c in keep_keys else f"avail_{norm_col(c)}" for c in df.columns]

    coerce_numeric_cols(df, ["avail_fpts", "avail_fp_per_g", "avail_ros", "avail_plus_minus"])
    return df


def build_fantrax_available_all() -> pd.DataFrame:
    files = sorted(FANTRAX_ALL_PLAYERS_DIR.glob("Fantrax_WeeklyStats_AvailablePlayers_GW*.csv"))
    if not files:
        raise FileNotFoundError(f"No available players files found in: {FANTRAX_ALL_PLAYERS_DIR}")

    frames = [parse_available_weekly(f) for f in files]
    avail = pd.concat(frames, ignore_index=True, sort=False)

    dup = avail.groupby(["season", "fantrax_gw", "fantrax_player_id"]).size()
    bad = dup[dup > 1]
    if len(bad) > 0:
        raise ValueError(f"Duplicate rows in available players data. Example:\n{bad.head(20)}")

    return avail


# =========================
# Fantrax: Team rosters weekly (rostered players only)
# =========================
def parse_roster_weekly(path: Path) -> pd.DataFrame:
    m = re.search(r"fantrax_weeklystats_([^_]+)_GW(\d+)\.csv$", path.name, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse manager/GW from filename: {path.name}")
    manager = _slug(m.group(1))
    gw = int(m.group(2))

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    markers = {'"","Goalkeeper"': "goalkeeper", '"","Outfielder"': "outfielder"}

    sections: list[pd.DataFrame] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line in markers:
            section = markers[line]
            i += 1
            if i >= len(lines):
                break
            header = list(csv.reader([lines[i]]))[0]
            i += 1

            rows = []
            while i < len(lines):
                l = lines[i].strip()
                if l == "" or l in markers:
                    break
                rows.append(list(csv.reader([lines[i]]))[0])
                i += 1

            df = pd.DataFrame(rows, columns=header)
            df["section"] = section
            sections.append(df)
        i += 1

    if not sections:
        raise ValueError(f"No GK/Outfielder sections detected in: {path.name}")

    df = pd.concat(sections, ignore_index=True, sort=False)

    if "Player" in df.columns:
        df = df[~df["Player"].astype(str).str.contains("Totals", case=False, na=False)]

    if "ID" not in df.columns:
        raise ValueError(f"{path.name}: missing ID column. Columns={list(df.columns)}")

    df = df[df["ID"].notna() & (df["ID"].astype(str).str.strip() != "")]

    df = df.rename(columns={"ID": "fantrax_player_id"})
    coerce_id_str(df, "fantrax_player_id")

    df["season"] = SEASON_STR
    df["fantrax_gw"] = gw
    df["manager"] = manager

    keep_keys = {"fantrax_player_id", "season", "fantrax_gw", "manager", "section"}
    df.columns = [c if c in keep_keys else f"mgr_{norm_col(c)}" for c in df.columns]

    coerce_numeric_cols(df, [
        "mgr_fantasy_points",
        "mgr_average_fantasy_points_per_game",
        "mgr_gp", "mgr_gs", "mgr_min"
    ])

    return df


def build_fantrax_rostered_all() -> pd.DataFrame:
    files = sorted(FANTRAX_TEAM_ROSTERS_DIR.glob("fantrax_weeklystats_*_GW*.csv"))
    if not files:
        raise FileNotFoundError(f"No team roster files found in: {FANTRAX_TEAM_ROSTERS_DIR}")

    frames = [parse_roster_weekly(f) for f in files]
    rostered = pd.concat(frames, ignore_index=True, sort=False)

    dup = rostered.groupby(["season", "fantrax_gw", "fantrax_player_id"]).size()
    bad = dup[dup > 1]
    if len(bad) > 0:
        raise ValueError(
            "Draft violation or parsing duplicate: same player appears multiple times in same GW.\n"
            f"Examples:\n{bad.head(30)}"
        )

    return rostered


# =========================
# Crosswalk + scoring periods
# =========================
def read_crosswalk() -> pd.DataFrame:
    df = _safe_read_csv(CROSSWALK_PATH)
    df.columns = [norm_col(c) for c in df.columns]

    rename = {}
    if "fantrax_player_id" not in df.columns and "fantrax_id" in df.columns:
        rename["fantrax_id"] = "fantrax_player_id"
    if "understat_player_id" not in df.columns and "understat_id" in df.columns:
        rename["understat_id"] = "understat_player_id"
    df = df.rename(columns=rename)

    need = {"fantrax_player_id", "understat_player_id"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"Crosswalk missing columns {missing}. Columns={list(df.columns)}")

    coerce_id_str(df, "fantrax_player_id")
    coerce_id_str(df, "understat_player_id")

    # Detect duplicates by fantrax_player_id (should be gone now, but keep safety)
    dup_mask = df["fantrax_player_id"].notna() & df.duplicated(subset=["fantrax_player_id"], keep=False)
    dupes = df[dup_mask].copy()
    if len(dupes) > 0:
        dupes.sort_values(["fantrax_player_id", "understat_player_id"]).to_csv(OUT_CROSSWALK_DUPES, index=False)
        print(f"WARNING: crosswalk has duplicate fantrax_player_id rows. Wrote: {OUT_CROSSWALK_DUPES} rows={len(dupes):,}")
        df["_has_us"] = df["understat_player_id"].notna().astype(int)
        df = df.sort_values(["fantrax_player_id", "_has_us"], ascending=[True, False])
        df = df.drop_duplicates(subset=["fantrax_player_id"], keep="first").drop(columns=["_has_us"])

    return df


def read_scoring_periods() -> pd.DataFrame:
    df = _safe_read_csv(SCORING_PERIODS_PATH)
    df.columns = [norm_col(c) for c in df.columns]

    rename = {}
    if "fantrax_gw" not in df.columns and "gw" in df.columns:
        rename["gw"] = "fantrax_gw"
    if "period_start" not in df.columns and "start" in df.columns:
        rename["start"] = "period_start"
    if "period_end" not in df.columns and "end" in df.columns:
        rename["end"] = "period_end"
    df = df.rename(columns=rename)

    need = {"season", "fantrax_gw", "period_start", "period_end"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"Scoring periods missing columns {missing}. Columns={list(df.columns)}")

    df["fantrax_gw"] = pd.to_numeric(df["fantrax_gw"], errors="coerce").astype("Int64")
    df["period_start"] = pd.to_datetime(df["period_start"], errors="coerce")
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    return df


# =========================
# Understat: weekly by Fantrax GW
# =========================
def read_understat_pms() -> pd.DataFrame:
    if not UNDERSTAT_PMS_CSV.exists():
        raise FileNotFoundError(f"Understat PMS CSV not found: {UNDERSTAT_PMS_CSV}")

    df = _safe_read_csv(UNDERSTAT_PMS_CSV)
    df.columns = [norm_col(c) for c in df.columns]

    if "player_id" in df.columns and "understat_player_id" not in df.columns:
        df = df.rename(columns={"player_id": "understat_player_id"})
    if "game_id" not in df.columns:
        raise ValueError(f"Understat PMS missing game_id. Columns={list(df.columns)}")
    if "kickoff_datetime" not in df.columns:
        raise ValueError(f"Understat PMS missing kickoff_datetime. Columns={list(df.columns)}")

    df["season"] = df.get("season", SEASON_STR)
    df["kickoff_datetime"] = pd.to_datetime(df["kickoff_datetime"], errors="coerce")

    coerce_id_str(df, "understat_player_id")
    coerce_id_str(df, "game_id")

    return df


def build_understat_weekly_by_fantrax_gw(periods: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    pms = read_understat_pms()
    x = pms.merge(periods, on="season", how="left", validate="many_to_many")

    x = x[
        (x["kickoff_datetime"] >= x["period_start"]) &
        (x["kickoff_datetime"] <  x["period_end"])
    ].copy()

    match_map_cols = ["season", "game_id", "fantrax_gw", "kickoff_datetime"]
    if "home_team" in x.columns:
        match_map_cols.append("home_team")
    if "away_team" in x.columns:
        match_map_cols.append("away_team")

    match_map = (
        x[match_map_cols]
        .drop_duplicates()
        .sort_values(["season", "fantrax_gw", "kickoff_datetime"])
        .reset_index(drop=True)
    )

    dup = match_map.groupby(["season", "game_id"]).size()
    bad = dup[dup > 1]
    if len(bad) > 0:
        raise ValueError(
            "Some matches mapped to multiple Fantrax GWs. Your scoring periods overlap.\n"
            f"Examples:\n{bad.head(20)}"
        )

    match_counts = (
        x.dropna(subset=["understat_player_id", "game_id"])
         .groupby(["season", "fantrax_gw", "understat_player_id"])["game_id"]
         .nunique()
         .reset_index(name="us_matches_in_gw")
    )

    id_cols = {"season", "fantrax_gw", "understat_player_id"}
    numeric_cols = x.select_dtypes(include="number").columns.tolist()
    numeric_cols = [c for c in numeric_cols if c not in id_cols]

    weekly = (
        x.groupby(["season", "fantrax_gw", "understat_player_id"], as_index=False)[numeric_cols]
        .sum(numeric_only=True)
        .merge(match_counts, on=["season", "fantrax_gw", "understat_player_id"], how="left")
    )

    coerce_id_str(weekly, "understat_player_id")
    return weekly, match_map


# =========================
# Master build
# =========================
def main():
    print("Building Fantrax available weekly…")
    avail = build_fantrax_available_all()
    avail.to_csv(OUT_FANTRAX_AVAILABLE, index=False)
    print(f"  wrote {OUT_FANTRAX_AVAILABLE} rows={len(avail):,}")

    print("Building Fantrax rostered weekly…")
    rostered = build_fantrax_rostered_all()
    rostered.to_csv(OUT_FANTRAX_ROSTERED, index=False)
    print(f"  wrote {OUT_FANTRAX_ROSTERED} rows={len(rostered):,}")

    print("Reading crosswalk + scoring periods…")
    crosswalk = read_crosswalk()
    periods = read_scoring_periods()

    print("Building Understat weekly by Fantrax scoring period…")
    understat_weekly, match_map = build_understat_weekly_by_fantrax_gw(periods)
    understat_weekly.to_csv(OUT_UNDERSTAT_WEEKLY, index=False)
    match_map.to_csv(OUT_UNDERSTAT_MATCH_MAP, index=False)
    print(f"  wrote {OUT_UNDERSTAT_WEEKLY} rows={len(understat_weekly):,}")
    print(f"  wrote {OUT_UNDERSTAT_MATCH_MAP} matches={match_map['game_id'].nunique():,}")

    print("Creating Fantrax master weekly (everyone + roster deep stats where rostered)…")
    fantrax_master = avail.merge(
        rostered,
        on=["season", "fantrax_gw", "fantrax_player_id"],
        how="left",
        validate="one_to_one"
    )

    # Attach crosswalk (fantrax -> understat)
    fantrax_master = fantrax_master.merge(
        crosswalk,
        on="fantrax_player_id",
        how="left",
        validate="many_to_one"
    )

    print("Merging Understat weekly into master…")
    # NOTE: fantrax_master contains MANY rows with understat_player_id = NA.
    # That makes left merge keys non-unique. So validation must be many_to_one.
    master = fantrax_master.merge(
        understat_weekly,
        on=["season", "fantrax_gw", "understat_player_id"],
        how="left",
        validate="many_to_one"
    )

    if FILL_UNDERSTAT_NA_WITH_ZERO:
        us_numeric = understat_weekly.select_dtypes(include="number").columns.tolist()
        us_numeric = [c for c in us_numeric if c not in ["fantrax_gw"]]
        for c in us_numeric:
            if c in master.columns:
                master[c] = master[c].fillna(0)

    print("Generating unmapped player reports…")
    fantrax_unmapped = master[master["understat_player_id"].isna()].copy()

    keep_cols = ["season", "fantrax_gw", "fantrax_player_id"]
    for c in ["avail_player", "avail_team", "avail_position", "avail_status"]:
        if c in fantrax_unmapped.columns:
            keep_cols.append(c)

    unmapped_f = fantrax_unmapped[keep_cols].drop_duplicates()
    unmapped_f.to_csv(OUT_UNMAPPED_FANTRAX, index=False)

    us_ids = set(understat_weekly["understat_player_id"].dropna().astype(str).tolist())
    mapped_us_ids = set(crosswalk["understat_player_id"].dropna().astype(str).tolist())
    missing_us_ids = sorted(us_ids - mapped_us_ids)
    unmapped_u = pd.DataFrame({"understat_player_id": missing_us_ids})

    try:
        pms = read_understat_pms()
        if "player_name" in pms.columns:
            name_map = (
                pms.dropna(subset=["understat_player_id"])
                   .groupby("understat_player_id")["player_name"]
                   .agg(lambda s: s.dropna().astype(str).iloc[0] if len(s.dropna()) else pd.NA)
                   .reset_index()
            )
            unmapped_u = unmapped_u.merge(name_map, on="understat_player_id", how="left")
        if "team_name" in pms.columns:
            team_map = (
                pms.dropna(subset=["understat_player_id"])
                   .groupby("understat_player_id")["team_name"]
                   .agg(lambda s: s.dropna().astype(str).iloc[0] if len(s.dropna()) else pd.NA)
                   .reset_index()
            )
            unmapped_u = unmapped_u.merge(team_map, on="understat_player_id", how="left")
    except Exception:
        pass

    unmapped_u.to_csv(OUT_UNMAPPED_UNDERSTAT, index=False)

    print(f"  wrote {OUT_UNMAPPED_FANTRAX} rows={len(unmapped_f):,}")
    print(f"  wrote {OUT_UNMAPPED_UNDERSTAT} rows={len(unmapped_u):,}")

    master.to_csv(OUT_MASTER, index=False)
    print(f"\n✅ Wrote master: {OUT_MASTER} rows={len(master):,}")

    rostered_pct = 100 * (1 - master["manager"].isna().mean()) if "manager" in master.columns else 0.0
    mapped_pct = 100 * (1 - master["understat_player_id"].isna().mean())

    print("\nSanity:")
    print(f"  Fantrax rows (player-weeks): {len(master):,}")
    print(f"  % rostered (has manager):    {rostered_pct:.1f}%")
    print(f"  % mapped to Understat id:    {mapped_pct:.1f}%")
    if "us_matches_in_gw" in master.columns:
        dgw_rows = int((master["us_matches_in_gw"].fillna(0) >= 2).sum())
        print(f"  rows with DGW (>=2 matches): {dgw_rows:,}")
    if OUT_CROSSWALK_DUPES.exists():
        print(f"  crosswalk duplicates report: {OUT_CROSSWALK_DUPES}")
    print("Done.")


if __name__ == "__main__":
    main()