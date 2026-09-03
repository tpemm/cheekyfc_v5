"""Central live-season configuration with secrets kept outside source control."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from config.project_paths import PROJECT_ROOT


CONFIG_PATH = PROJECT_ROOT / "config" / "live_season_2627.json"
RETIRED_LEAGUE_IDS = frozenset({"rg1i70pfmdhjhvn3"})


def _mapping_value(values: Mapping[str, Any] | None, name: str) -> str | None:
    if not values:return None
    direct=str(values.get(name,"")).strip()
    if direct:return direct
    fantrax=values.get("fantrax",{})
    return str(fantrax.get(name,"")).strip() or None if isinstance(fantrax,Mapping) else None


def _runtime_streamlit_secrets() -> Mapping[str, Any] | None:
    """Read deployed/local Streamlit secrets when a Streamlit runtime is available."""
    try:
        import streamlit as st
        return st.secrets
    except Exception:
        return None


def resolve_live_league_id(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
    secrets: Mapping[str, Any] | None = None,
    secrets_path: str | Path | None = None,
    project_root: str | Path = PROJECT_ROOT,
) -> str | None:
    """Resolve environment, Streamlit secrets, then local TOML—never retired IDs."""
    environment=os.environ if environ is None else environ
    value=str(environment.get(name,"")).strip() or None
    path=Path(secrets_path) if secrets_path is not None else Path(project_root)/".streamlit"/"secrets.toml"
    if value is None and secrets is not None:value=_mapping_value(secrets,name)
    if value is None and path.exists():
        with path.open("rb") as handle:value=_mapping_value(tomllib.load(handle),name)
    if value is None and secrets is None:value=_mapping_value(_runtime_streamlit_secrets(),name)
    if value in RETIRED_LEAGUE_IDS:
        raise ValueError("The retired 2025/26 Fantrax league ID cannot be used for season 2627")
    return value


@dataclass(frozen=True, slots=True)
class LiveSeasonConfig:
    season_id: str
    league_name: str
    league_id_env: str
    league_id: str | None
    manager_count: int
    period_minimum: int
    period_maximum: int
    roster_limits: dict[str, int]
    starting_lineup: dict[str, int]
    manager_team_identifiers: tuple[dict[str, Any], ...]
    status: str
    raw_root: Path
    model_root: Path
    quality_root: Path

    def require_league_id(self) -> str:
        if not self.league_id:
            raise RuntimeError(
                f"Set {self.league_id_env} before refreshing Fantrax. "
                "The retired 2025/26 league ID is intentionally not reused."
            )
        return self.league_id

    def validate_period(self, period: int) -> int:
        value = int(period)
        if not self.period_minimum <= value <= self.period_maximum:
            raise ValueError(
                f"Period {value} is outside {self.period_minimum}-{self.period_maximum}"
            )
        return value


def load_live_season_config(
    path: str | Path = CONFIG_PATH,
    *,
    environ: dict[str, str] | None = None,
    secrets: Mapping[str, Any] | None = None,
    secrets_path: str | Path | None = None,
    project_root: str | Path = PROJECT_ROOT,
) -> LiveSeasonConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    season_id = str(payload["season_id"])
    if season_id != "2627":
        raise ValueError("Live-season configuration must target season 2627")
    env_name = str(payload["league_id_env"])
    root = Path(project_root)
    league_id=resolve_live_league_id(env_name,environ=environ,secrets=secrets,secrets_path=secrets_path,project_root=root)
    periods = payload["scoring_periods"]
    return LiveSeasonConfig(
        season_id=season_id,
        league_name=str(payload["league_name"]),
        league_id_env=env_name,
        league_id=league_id,
        manager_count=int(payload["manager_count"]),
        period_minimum=int(periods["minimum"]),
        period_maximum=int(periods["maximum"]),
        roster_limits={key: int(value) for key, value in payload["roster_limits"].items()},
        starting_lineup={key: int(value) for key, value in payload["starting_lineup"].items()},
        manager_team_identifiers=tuple(payload.get("manager_team_identifiers", [])),
        status=str(payload["status"]),
        raw_root=root / "data" / "raw" / "fantrax" / season_id,
        model_root=root / "data" / "models" / f"season_{season_id}",
        quality_root=root / "data" / "quality" / f"season_{season_id}",
    )
