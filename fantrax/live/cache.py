"""Validated, atomic raw Fantrax cache writes."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from fantrax.live.config import LiveSeasonConfig


def cache_filename(request_type: str, config: LiveSeasonConfig, *, period: int | None = None, date_key: str | None = None) -> str:
    safe = request_type.strip().lower().replace(" ", "_")
    if period is not None:
        return f"{safe}_{config.season_id}_period_{config.validate_period(period):02d}.json"
    if date_key is not None:
        return f"{safe}_{config.season_id}_{date_key}.json"
    return f"{safe}_{config.season_id}_latest.json"


def cache_path(config: LiveSeasonConfig, category: str, request_type: str, **parts: Any) -> Path:
    return config.raw_root / category / cache_filename(request_type, config, **parts)


def write_validated_json(
    path: Path,
    payload: Any,
    *,
    config: LiveSeasonConfig,
    request_type: str,
    source: str,
    validator: Callable[[Any], None],
    retrieved_at: datetime | None = None,
) -> dict[str, Any]:
    """Validate in memory, then atomically replace the prior valid artifact."""
    validator(payload)
    timestamp = retrieved_at or datetime.now(timezone.utc)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    metadata = {
        "source": source,
        "retrieved_at": timestamp.isoformat(),
        "season_id": config.season_id,
        "league_id": config.league_id,
        "request_type": request_type,
        "validation_status": "valid",
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_tmp = path.with_suffix(path.suffix + ".tmp")
    metadata_path = path.with_suffix(path.suffix + ".metadata.json")
    metadata_tmp = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    payload_tmp.write_bytes(encoded)
    metadata_tmp.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    payload_tmp.replace(path)
    metadata_tmp.replace(metadata_path)
    return metadata


def refresh_json(
    path: Path,
    fetcher: Callable[[], Any],
    **write_kwargs: Any,
) -> dict[str, Any]:
    """Fetch then validate/write; a fetch or validation error leaves cache intact."""
    payload = fetcher()
    return write_validated_json(path, payload, **write_kwargs)
