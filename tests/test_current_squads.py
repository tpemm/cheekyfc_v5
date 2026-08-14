import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from analytics.current_squads.cache import read_snapshot, write_snapshot
from analytics.current_squads.fpl_provider import (
    FPLCurrentSquadProvider,
    FPL_BOOTSTRAP_URL,
)
from analytics.current_squads.model import CurrentSquadError, CurrentSquadSchemaError


@pytest.fixture
def project_path():
    path = Path.cwd() / ".test_artifacts" / f"current_squads_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def payload(players=None, teams=None):
    return {
        "teams": teams
        or [{"id": i, "name": f"Team {i}", "short_name": f"T{i:02}"} for i in range(1, 21)],
        "elements": players
        or [
            {
                "id": i,
                "first_name": f"First{i}",
                "second_name": f"Last{i}",
                "team": i,
                "element_type": (i % 4) + 1,
                "status": "a",
                "news": "",
            }
            for i in range(1, 21)
        ],
    }


def provider_for(value):
    return FPLCurrentSquadProvider(
        "2627",
        downloader=lambda url, timeout: json.dumps(value).encode(),
        retrieved_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )


def test_fpl_provider_downloads_normalizes_and_validates():
    frame = provider_for(payload()).fetch_players()
    assert len(frame) == 20
    assert frame["team_code"].nunique() == 20
    assert frame["provider"].eq("Official FPL API").all()
    assert frame["season_id"].eq("2627").all()


def test_fpl_endpoint_and_timeout_are_passed():
    calls = []
    value = payload()
    provider = FPLCurrentSquadProvider(
        "2627",
        timeout=7,
        downloader=lambda url, timeout: calls.append((url, timeout))
        or json.dumps(value).encode(),
    )
    provider.fetch_players()
    assert calls == [(FPL_BOOTSTRAP_URL, 7)]


@pytest.mark.parametrize(
    "value",
    [{}, {"teams": [], "elements": []}, {"teams": [], "elements": [{}]}],
)
def test_malformed_or_empty_response_is_rejected(value):
    with pytest.raises(CurrentSquadSchemaError):
        provider_for(value).fetch_players()


def test_timeout_is_wrapped():
    provider = FPLCurrentSquadProvider(
        "2627",
        downloader=lambda *_: (_ for _ in ()).throw(TimeoutError("late")),
    )
    with pytest.raises(CurrentSquadError, match="late"):
        provider.fetch_players()


def test_duplicate_player_ids_are_rejected():
    value = payload()
    value["elements"].append(dict(value["elements"][0]))
    with pytest.raises(CurrentSquadSchemaError, match="duplicate"):
        provider_for(value).fetch_players()


def test_snapshot_round_trip_and_metadata(project_path):
    frame = provider_for(payload()).fetch_players()
    path = project_path / "players.csv"
    metadata = project_path / "players.json"
    write_snapshot(frame, path, metadata)
    loaded = read_snapshot(path)
    assert loaded["provider_player_id"].astype(str).tolist() == frame["provider_player_id"].tolist()
    details = json.loads(metadata.read_text())
    assert details["player_count"] == 20
    assert details["team_count"] == 20
