"""Season-versioned resolver for commissioner-provided Fantrax scoring rules."""
from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
POSITION_ALIASES = {"GK":"G","GOALKEEPER":"G","DEF":"D","DEFENDER":"D","MID":"M","MIDFIELDER":"M","FWD":"F","FORWARD":"F","ST":"F"}

def normalize_scoring_position(value: object) -> str:
    text = "" if value is None else str(value).strip().upper()
    text = POSITION_ALIASES.get(text, text)
    return text if text in {"G", "D", "M", "F"} else ""

@lru_cache(maxsize=None)
def load_scoring_config(season: str = "2627") -> dict:
    key = str(season).replace("/", "").strip()
    path = ROOT / "config" / f"fantrax_scoring_{key}.json"
    if not path.exists():
        raise KeyError(f"No Fantrax scoring configuration for season {season!r}")
    config = json.loads(path.read_text(encoding="utf-8"))
    if str(config.get("season")) != key:
        raise ValueError(f"Scoring config season mismatch in {path}")
    return config

def get_rule(season: str, position: object, stat: str) -> dict:
    pos = normalize_scoring_position(position)
    if not pos:
        raise ValueError(f"Unknown scoring position: {position!r}")
    config = load_scoring_config(season)
    position_config = config["positions"][pos]
    code = str(stat).strip()
    rule = position_config.get("overrides", {}).get(code)
    if rule is None:
        rule = config["profiles"][position_config["inherits"]]["rules"].get(code)
    if rule is None:
        raise KeyError(f"No {season} scoring rule for {pos}/{code}")
    return rule

def score_stat(season: str, position: object, stat: str, value: object) -> float:
    try:
        count = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Non-numeric value for {stat}: {value!r}") from None
    if not math.isfinite(count):
        raise ValueError(f"Non-finite value for {stat}: {value!r}")
    rule = get_rule(season, position, stat)
    if rule["type"] == "flat":
        return count * float(rule["points_each"])
    if rule["type"] == "cumulative_ranges":
        if count <= 0:
            return 0.0
        total = 0.0
        for band in rule["ranges"]:
            start = float(band["from"])
            end = float(band.get("to", count))
            units = max(min(count, end) - start + 1.0, 0.0)
            total += units * float(band["points_each"])
        return total
    raise ValueError(f"Unsupported scoring rule type: {rule['type']!r}")

def effective_rules(season: str = "2627") -> list[dict]:
    config = load_scoring_config(season)
    stats = sorted({s for p in config["profiles"].values() for s in p["rules"]} | {s for p in config["positions"].values() for s in p.get("overrides", {})})
    rows = []
    for stat in stats:
        row = {"stat": stat, "source": config["source"]}
        types = set()
        overridden = []
        for pos in ("G", "D", "M", "F"):
            try:
                rule = get_rule(season, pos, stat)
                row[pos] = json.dumps(rule, separators=(",", ":"))
                types.add(rule["type"])
                if stat in config["positions"][pos].get("overrides", {}): overridden.append(pos)
            except KeyError:
                row[pos] = ""
        row["rule_type"] = ",".join(sorted(types)); row["override_status"] = ",".join(overridden) or "inherited"
        rows.append(row)
    return rows
