import json,zipfile
from pathlib import Path
import pytest
import uuid
from core.services.machine_role import get_machine_role,require_commissioner_writer,MachineRoleError
from fantrax.migration.package import build_package,import_package,validate_package
from streamlit.testing.v1 import AppTest

@pytest.fixture
def workdir():
    path=Path(__file__).parents[1]/".test_artifacts"/f"migration_{uuid.uuid4().hex}";path.mkdir(parents=True);return path

def test_machine_role_allows_commissioner_and_rejects_client_before_write(workdir):
    require_commissioner_writer("test",{"FANTRAX_MACHINE_ROLE":"commissioner","COMMISSIONER_REFRESH_ENABLED":"true"})
    marker=workdir/"write"
    with pytest.raises(MachineRoleError):
        require_commissioner_writer("test",{"FANTRAX_MACHINE_ROLE":"client","COMMISSIONER_REFRESH_ENABLED":"false"});marker.write_text("bad")
    assert not marker.exists() and get_machine_role({"FANTRAX_MACHINE_ROLE":"client"}).role=="client"

def fixture_root(workdir):
    root=workdir/"arbitrary-location";(root/"data/models/season_2627").mkdir(parents=True);(root/"data/quality/season_2627").mkdir(parents=True);(root/"data/raw/fantrax/2627/auth").mkdir(parents=True)
    (root/"data/models/season_2627/example.csv").write_text("a\n1\n");(root/"data/raw/fantrax/cache.json").write_text("{}");(root/"data/raw/fantrax/2627/auth/storage_state.json").write_text("SECRET")
    (root/"data/quality/season_2627/gw2_laptop_migration_checkpoint_repaired.json").write_text("{}")
    return root

def test_package_relative_hashes_secret_exclusion_and_dry_run(workdir):
    root=fixture_root(workdir);package=workdir/"state.zip";manifest=build_package(root,package)
    assert all(not Path(x["relative_path"]).is_absolute() for x in manifest["files"]);assert not any("storage_state" in x["relative_path"] for x in manifest["files"])
    assert validate_package(package)["package_version"]==1
    destination=workdir/"desktop";destination.mkdir();result=import_package(package,destination,check=True);assert result["status"]=="VALID" and not (destination/"data").exists()

def test_corruption_missing_file_and_path_traversal_rejected(workdir):
    root=fixture_root(workdir);package=workdir/"state.zip";build_package(root,package)
    with zipfile.ZipFile(package,"a") as z:z.writestr("data/models/season_2627/example.csv","corrupt")
    with pytest.raises(ValueError):validate_package(package)
    missing=workdir/"missing.zip"
    with zipfile.ZipFile(missing,"w") as z:
        z.writestr("desktop_migration_manifest.json",json.dumps({"package_version":1,"files":[{"relative_path":"data/missing.csv","sha256":"x"}]}))
    with pytest.raises(FileNotFoundError):validate_package(missing)
    package2=workdir/"unsafe.zip"
    with zipfile.ZipFile(package2,"w") as z:z.writestr("desktop_migration_manifest.json",json.dumps({"package_version":1,"files":[{"relative_path":"../bad","sha256":"x"}]}))
    with pytest.raises(ValueError):validate_package(package2)

def test_commit_mismatch_is_warning_not_import_failure(workdir,monkeypatch):
    root=fixture_root(workdir);package=workdir/"state.zip";monkeypatch.setattr("fantrax.migration.package.git_commit",lambda root:"source");build_package(root,package);destination=workdir/"desktop";destination.mkdir()
    monkeypatch.setattr("fantrax.migration.package.git_commit",lambda root:"different")
    assert import_package(package,destination,check=True)["warnings"]

def test_client_mode_can_start_normal_app(monkeypatch):
    monkeypatch.setenv("FANTRAX_MACHINE_ROLE","client");monkeypatch.setenv("COMMISSIONER_REFRESH_ENABLED","false")
    app=AppTest.from_file(str(Path(__file__).parents[1]/"app.py"),default_timeout=30).run()
    assert not app.exception
