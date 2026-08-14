from pathlib import Path
import shutil
import uuid

import pytest

from core.storage.local_filesystem_provider import LocalFilesystemProvider
from core.storage.storage_provider import ArtifactAccessError, StorageProvider


@pytest.fixture
def sandbox_path():
    path = Path.cwd() / ".test_artifacts" / f"storage_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_local_provider_implements_storage_contract(sandbox_path):
    provider = LocalFilesystemProvider()

    assert isinstance(provider, StorageProvider)
    assert provider.normalize(sandbox_path) == sandbox_path.resolve()


def test_text_bytes_exists_and_stat(sandbox_path):
    provider = LocalFilesystemProvider()
    artifact = sandbox_path / "sample.txt"
    artifact.write_text("hello", encoding="utf-8")

    assert provider.exists(artifact)
    assert provider.read_text(artifact) == "hello"
    assert provider.read_bytes(artifact) == b"hello"
    assert provider.stat(artifact).st_size == 5


def test_file_listing_is_deterministic_and_supports_patterns(sandbox_path):
    provider = LocalFilesystemProvider()
    (sandbox_path / "b.csv").write_text("value\n2\n", encoding="utf-8")
    (sandbox_path / "a.csv").write_text("value\n1\n", encoding="utf-8")
    nested = sandbox_path / "nested"
    nested.mkdir()
    (nested / "c.csv").write_text("value\n3\n", encoding="utf-8")

    direct = provider.list_files(sandbox_path, "*.csv")
    recursive = provider.list_files(sandbox_path, "*.csv", recursive=True)

    assert [path.name for path in direct] == ["a.csv", "b.csv"]
    assert [path.name for path in recursive] == ["a.csv", "b.csv", "c.csv"]


def test_missing_directory_lists_as_empty(sandbox_path):
    provider = LocalFilesystemProvider()

    assert provider.list_files(sandbox_path / "missing") == ()


def test_listing_a_file_as_root_is_rejected(sandbox_path):
    provider = LocalFilesystemProvider()
    artifact = sandbox_path / "sample.txt"
    artifact.write_text("hello", encoding="utf-8")

    with pytest.raises(ArtifactAccessError, match="not a directory"):
        provider.list_files(artifact)
