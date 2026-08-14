import json
import os
from pathlib import Path
import shutil
import uuid

import pandas as pd
import pytest

from core.models.data_result import DataStatus
from core.models.dataset_definition import DatasetDefinition
from core.services.data_manager import (
    DataManager,
    DataManagerError,
    DatasetNotFoundError,
    UnsupportedFormatError,
)
from core.services.dataset_registry import DatasetRegistry
from core.services.season_manager import SeasonManager
from core.storage.local_filesystem_provider import LocalFilesystemProvider


SEASONS = {
    "active": {
        "label": "Active",
        "status": "active",
        "enabled": True,
        "data_ready": True,
    },
    "historic": {
        "label": "Historic",
        "status": "finalized",
        "enabled": True,
        "data_ready": True,
    },
}


class CountingStorage(LocalFilesystemProvider):
    def __init__(self):
        self.byte_reads = 0

    def read_bytes(self, path):
        self.byte_reads += 1
        return super().read_bytes(path)


def definition(
    key: str,
    filename: str,
    *,
    required: bool = True,
    aliases: tuple[str, ...] = (),
    required_columns: tuple[str, ...] = (),
    family: bool = False,
    cacheable: bool = True,
) -> DatasetDefinition:
    return DatasetDefinition(
        key=key,
        display_name=key.replace("_", " ").title(),
        description=f"Test dataset {key}.",
        classification="processed",
        namespace="processed",
        filename_template=filename,
        required=required,
        aliases=aliases,
        cacheable=cacheable,
        schema_name=key,
        working_subdirectory="processed",
        snapshot_subdirectory="processed",
        required_columns=required_columns,
        family=family,
    )


@pytest.fixture
def sandbox_path():
    path = Path.cwd() / ".test_artifacts" / f"data_manager_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def services(sandbox_path):
    definitions = (
        definition(
            "players",
            "players_{season_id}.csv",
            aliases=("legacy_players",),
            required_columns=("player_id", "name"),
        ),
        definition("settings", "settings.json"),
        definition("report", "report.txt"),
        definition("table", "table.parquet"),
        definition("optional", "optional.csv", required=False),
        definition("empty", "empty.csv"),
        definition("binary", "binary.bin"),
        definition(
            "weekly",
            "weekly_GW*.csv",
            family=True,
            required=False,
        ),
    )
    registry = DatasetRegistry(definitions)
    seasons = SeasonManager(
        definitions=SEASONS,
        default_season_id="active",
        project_root=sandbox_path,
    )
    storage = CountingStorage()
    manager = DataManager(registry, seasons, storage)
    return manager, storage, sandbox_path


def working_processed(root: Path) -> Path:
    path = root / "data" / "processed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_processed(root: Path) -> Path:
    path = root / "data" / "seasons" / "historic" / "processed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_canonical_alias_and_namespace_path_resolution(services):
    manager, _, root = services

    working = manager.resolve_path("players", "active")
    alias = manager.resolve_path("legacy_players", "active")
    snapshot = manager.resolve_path("players", "historic")

    assert working == (root / "data/processed/players_active.csv").resolve()
    assert alias == working
    assert snapshot == (
        root / "data/seasons/historic/processed/players_historic.csv"
    ).resolve()
    assert (
        manager.project_relative_path("players", "historic")
        == str(Path("data/seasons/historic/processed/players_historic.csv"))
    )


def test_csv_loading_validation_and_alias_provenance(services):
    manager, _, root = services
    path = working_processed(root) / "players_active.csv"
    path.write_text("player_id,name\n1,Ada\n2,Bea\n", encoding="utf-8")

    result = manager.load_frame("legacy_players", "active")

    assert result.status is DataStatus.AVAILABLE
    assert result.data["name"].tolist() == ["Ada", "Bea"]
    assert result.provenance.dataset_key == "players"
    assert result.provenance.requested_key == "legacy_players"
    assert result.provenance.alias_used
    assert result.provenance.namespace == "working"
    assert result.provenance.size_bytes == path.stat().st_size


def test_json_and_text_loading(services):
    manager, _, root = services
    folder = working_processed(root)
    (folder / "settings.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8"
    )
    (folder / "report.txt").write_text("line one\nline two", encoding="utf-8")

    json_result = manager.load_json("settings", "active")
    text_result = manager.load_text("report", "active")

    assert json_result.data == {"enabled": True}
    assert text_result.data == "line one\nline two"
    assert json_result.provenance.format == "json"
    assert text_result.provenance.format == "txt"


def test_parquet_loading_when_engine_is_available(services):
    pytest.importorskip("pyarrow")
    manager, _, root = services
    path = working_processed(root) / "table.parquet"
    pd.DataFrame({"value": [1, 2]}).to_parquet(path, index=False)

    result = manager.load_frame("table", "active")

    assert result.status is DataStatus.AVAILABLE
    assert result.data["value"].tolist() == [1, 2]


def test_optional_missing_is_structured_and_required_missing_raises(services):
    manager, _, _ = services

    optional = manager.load("optional", "active")

    assert optional.status is DataStatus.MISSING
    assert optional.data is None
    with pytest.raises(DatasetNotFoundError, match="Required dataset"):
        manager.load("players", "active")

    required_probe = manager.probe("players", "active")
    optional_probe = manager.probe("optional", "active")
    assert required_probe.status is DataStatus.MISSING
    assert required_probe.validation_errors == ("Required dataset is missing.",)
    assert optional_probe.status is DataStatus.MISSING
    assert optional_probe.warnings == ("Optional dataset is missing.",)


def test_empty_file_and_required_column_validation(services):
    manager, _, root = services
    folder = working_processed(root)
    (folder / "empty.csv").write_bytes(b"")
    (folder / "players_active.csv").write_text(
        "player_id\n1\n", encoding="utf-8"
    )

    empty = manager.load("empty", "active")
    invalid = manager.load_frame("players", "active")

    assert empty.status is DataStatus.EMPTY
    assert empty.validation_errors == ("Artifact is empty.",)
    assert invalid.status is DataStatus.INVALID
    assert invalid.validation_errors == ("Missing required columns: name",)


def test_unsupported_format_is_rejected(services):
    manager, _, root = services
    (working_processed(root) / "binary.bin").write_bytes(b"\x00\x01")

    with pytest.raises(UnsupportedFormatError, match="Unsupported format"):
        manager.load("binary", "active")


def test_metadata_inspection(services):
    manager, _, root = services
    path = working_processed(root) / "report.txt"
    path.write_text("hello", encoding="utf-8")

    info = manager.inspect("report", "active")

    assert info is not None
    assert info.path == path.resolve()
    assert info.name == "report.txt"
    assert info.suffix == ".txt"
    assert info.size_bytes == 5
    assert info.dataset_key == "report"


def test_preview_applies_row_and_column_limits(services):
    manager, _, root = services
    path = working_processed(root) / "players_active.csv"
    path.write_text(
        "player_id,name,score\n1,Ada,3\n2,Bea,4\n3,Cia,5\n",
        encoding="utf-8",
    )

    result = manager.preview(
        "players",
        "active",
        row_limit=2,
        column_limit=2,
    )

    assert result.data.shape == (2, 2)
    assert result.data.columns.tolist() == ["player_id", "name"]
    assert len(result.warnings) == 2


def test_catalog_excludes_sensitive_and_unsupported_artifacts(services):
    manager, _, root = services
    data_root = root / "data"
    folder = working_processed(root)
    safe = folder / "safe.csv"
    safe.write_text("value\n1\n", encoding="utf-8")
    (folder / "fantrax_auth_state.json").write_text("{}", encoding="utf-8")
    (folder / "api_secret.txt").write_text("hidden", encoding="utf-8")
    (folder / "driver.lock").write_text("locked", encoding="utf-8")
    (folder / "image.png").write_bytes(b"png")
    (data_root / ".env").write_text("SECRET=value", encoding="utf-8")

    artifacts = manager.catalog("active")
    names = {artifact.name for artifact in artifacts}

    assert "safe.csv" in names
    assert "fantrax_auth_state.json" not in names
    assert "api_secret.txt" not in names
    assert "driver.lock" not in names
    assert "image.png" not in names
    assert ".env" not in names


def test_catalog_artifact_preview_supports_unregistered_formats(services):
    manager, _, root = services
    folder = working_processed(root)
    (folder / "browse.csv").write_text(
        "name,value\nAda,1\nBea,2\nCia,3\n",
        encoding="utf-8",
    )
    (folder / "browse.json").write_text(
        json.dumps([{"name": "Ada"}, {"name": "Bea"}]),
        encoding="utf-8",
    )
    (folder / "browse.txt").write_text(
        "line one\nline two\nline three",
        encoding="utf-8",
    )
    artifacts = {item.name: item for item in manager.catalog("active")}

    csv_result = manager.preview_artifact(
        artifacts["browse.csv"],
        "active",
        row_limit=2,
    )
    json_result = manager.preview_artifact(
        artifacts["browse.json"],
        "active",
        row_limit=1,
    )
    text_result = manager.preview_artifact(
        artifacts["browse.txt"],
        "active",
        row_limit=2,
    )

    assert csv_result.data["name"].tolist() == ["Ada", "Bea"]
    assert json_result.data == [{"name": "Ada"}]
    assert text_result.data == "line one\nline two"


def test_catalog_artifact_preview_rejects_other_namespace(services):
    manager, _, root = services
    path = working_processed(root) / "safe.csv"
    path.write_text("value\n1\n", encoding="utf-8")
    artifact = next(
        item for item in manager.catalog("active") if item.name == "safe.csv"
    )

    with pytest.raises(DataManagerError, match="outside"):
        manager.preview_artifact(artifact, "historic")


def test_family_loading_is_deterministic_and_filterable(services):
    manager, _, root = services
    folder = working_processed(root)
    (folder / "weekly_GW02.csv").write_text("value\n2\n", encoding="utf-8")
    (folder / "weekly_GW01.csv").write_text("value\n1\n", encoding="utf-8")

    all_members = manager.load_family("weekly", "active")
    filtered = manager.load_family(
        "weekly", "active", filters={"name_contains": "GW02"}
    )

    assert all_members.status is DataStatus.AVAILABLE
    assert [
        member.provenance.resolved_path.name for member in all_members.data
    ] == ["weekly_GW01.csv", "weekly_GW02.csv"]
    assert len(filtered.data) == 1
    assert filtered.data[0].data["value"].iloc[0] == 2

    inspected = manager.inspect_family("weekly", "active")
    assert [artifact.name for artifact in inspected] == [
        "weekly_GW01.csv",
        "weekly_GW02.csv",
    ]
    assert manager.project_relative_artifact_path(
        inspected[0].path,
        "active",
    ) == str(Path("data/processed/weekly_GW01.csv"))

    exact = manager.load_family(
        "weekly",
        "active",
        filters={"name": "weekly_GW02.csv", "limit": 1},
    )
    assert len(exact.data) == 1
    assert exact.data[0].data["value"].iloc[0] == 2


def test_empty_family_has_clear_result(services):
    manager, _, _ = services

    result = manager.load_family("weekly", "active")

    assert result.status is DataStatus.MISSING
    assert result.data == ()


def test_cache_hit_defensive_copy_and_file_change_invalidation(services):
    manager, storage, root = services
    path = working_processed(root) / "players_active.csv"
    path.write_text("player_id,name\n1,Ada\n", encoding="utf-8")

    first = manager.load_frame("players", "active")
    first.data.loc[0, "name"] = "Changed by caller"
    second = manager.load_frame("players", "active")

    assert storage.byte_reads == 1
    assert second.data.loc[0, "name"] == "Ada"
    assert first.data is not second.data

    path.write_text("player_id,name\n1,Eve\n", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    third = manager.load_frame("players", "active")

    assert storage.byte_reads == 2
    assert third.data.loc[0, "name"] == "Eve"

    manager.invalidate("players", "active")
    manager.load_frame("players", "active")
    assert storage.byte_reads == 3


def test_invalid_season_propagates_and_finalized_snapshot_is_readable(services):
    manager, _, root = services

    with pytest.raises(KeyError, match="Unknown season ID"):
        manager.load("players", "missing")

    path = snapshot_processed(root) / "players_historic.csv"
    path.write_text("player_id,name\n1,Ada\n", encoding="utf-8")
    result = manager.load_frame("players", "historic")

    assert result.status is DataStatus.AVAILABLE
    assert result.provenance.namespace == "snapshot"


def test_data_manager_exposes_no_public_write_api(services):
    manager, _, _ = services

    for method_name in ("save", "write", "write_frame", "write_json"):
        assert not hasattr(manager, method_name)


def test_singular_load_rejects_family_definition(services):
    manager, _, _ = services

    with pytest.raises(DataManagerError, match="use load_family"):
        manager.load("weekly", "active")
