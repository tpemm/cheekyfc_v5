"""Local bare remotes exercise publishing without network or live acquisition."""
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from core.services import refresh_publisher as pub

GIT = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
DATA = "data/models/season_2627/current_player_weekly_2627.csv"
ENV = {"FANTRAX_MACHINE_ROLE": "commissioner", "COMMISSIONER_REFRESH_ENABLED": "true"}


def git(root, *args):
    return subprocess.check_output([GIT, *args], cwd=root, stderr=subprocess.PIPE, text=True).strip()


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", str(remote))
    root = tmp_path / "work"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    (root / DATA).parent.mkdir(parents=True)
    (root / DATA).write_text("player,points\nExample,1\n")
    (root / "app.py").write_text("# baseline\n")
    git(root, "add", "app.py", DATA)
    git(root, "commit", "-m", "baseline")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-u", "origin", "main")
    return root


def publish(repo, **kwargs):
    return pub.publish_refresh(repo, current_gw=3, refresh_status=kwargs.pop("refresh_status", "PASS"),
                               env=kwargs.pop("env", ENV), **kwargs)


def change(repo):
    (repo / DATA).write_text("player,points\nExample,2\n")


@pytest.mark.parametrize("env", [
    {"FANTRAX_MACHINE_ROLE": "client", "COMMISSIONER_REFRESH_ENABLED": "true"},
    {"FANTRAX_MACHINE_ROLE": "commissioner", "COMMISSIONER_REFRESH_ENABLED": "false"},
    {"FANTRAX_MACHINE_ROLE": "commissioner"},
])
def test_role_guard(repo, env):
    assert publish(repo, env=env).status == "BLOCKED"


@pytest.mark.parametrize("status", ["FAIL", "PARTIAL", "FAILED"])
def test_failed_refresh_blocks(repo, status):
    change(repo)
    assert publish(repo, refresh_status=status).status == "BLOCKED"
    assert not git(repo, "diff", "--cached", "--name-only")


@pytest.mark.parametrize("status", ["PASS", "CACHE_HIT", "NO_ACTION_REQUIRED"])
def test_no_changes(repo, status):
    assert publish(repo, refresh_status=status).status == "NO_ACTION_REQUIRED"


def test_dirty_source_blocks_exact_path(repo):
    change(repo)
    (repo / "app.py").write_text("# user edits\n")
    result = publish(repo, dry_run=True)
    assert result.files == (DATA,)
    assert "Unrelated dirty path: app.py" in result.blockers
    assert not git(repo, "diff", "--cached", "--name-only")


def test_untracked_source_blocks(repo):
    (repo / "new.py").write_text("# uncommitted source\n")
    assert "Uncommitted source path: new.py" in publish(repo).blockers


@pytest.mark.parametrize("diverged", [False, True])
def test_remote_moved(repo, diverged):
    old = git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "--allow-empty", "-m", "remote advance")
    git(repo, "push", "origin", "main")
    # Only the disposable fixture's branch is moved backwards.
    git(repo, "update-ref", "refs/heads/main", old)
    if diverged:
        git(repo, "commit", "--allow-empty", "-m", "local advance")
    result = publish(repo)
    assert result.status == "BLOCKED"
    assert any("behind or diverged" in b for b in result.blockers)


def test_unpushed_source_commit_blocks(repo):
    git(repo, "commit", "--allow-empty", "-m", "local source")
    assert any("unpushed commits" in b for b in publish(repo).blockers)


def test_dry_run_is_read_only_and_builds_plan(repo):
    change(repo)
    head = git(repo, "rev-parse", "HEAD")
    index = (repo / ".git/index").read_bytes()
    result = publish(repo, dry_run=True)
    assert result.status == "DRY_RUN" and result.files == (DATA,)
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "rev-parse", "origin/main") == head
    assert (repo / ".git/index").read_bytes() == index


def test_raw_auth_never_staged_even_if_manifest_contains_it(repo, tmp_path, monkeypatch):
    path = "data/raw/fantrax/auth_state.json"
    (repo / path).parent.mkdir(parents=True)
    (repo / path).write_text('{"cookies": []}')
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"season": "2627", "paths": [DATA, path]}))
    monkeypatch.setattr(pub, "MANIFEST", manifest)
    change(repo)
    result = publish(repo)
    assert result.status == "PUBLISHED"
    assert git(repo, "show", "--format=", "--name-only", "HEAD") == DATA
    assert not git(repo, "ls-files", path)


def test_preexisting_staged_raw_auth_blocks(repo):
    path = "data/raw/auth.json"
    (repo / path).parent.mkdir(parents=True)
    (repo / path).write_text("{}")
    git(repo, "add", path)
    assert publish(repo).status == "BLOCKED"
    assert git(repo, "diff", "--cached", "--name-only") == path


def test_secret_content_blocks_before_staging(repo):
    (repo / DATA).write_text('{"access_token":"not-for-publication"}')
    assert publish(repo).status == "BLOCKED"
    assert not git(repo, "diff", "--cached", "--name-only")


def test_successful_commit_and_verified_push(repo):
    change(repo)
    result = publish(repo)
    assert result.status == "PUBLISHED"
    assert result.commit == git(repo, "rev-parse", "HEAD")
    assert git(repo, "ls-remote", "origin", "refs/heads/main").split()[0] == result.commit
    assert git(repo, "log", "-1", "--format=%s") == f"Data refresh: GW3 {datetime.now().date().isoformat()}"
    assert not git(repo, "status", "--porcelain")


def test_new_current_gw_correction_evidence_is_planned(repo):
    path = "data/quality/season_2627/fantrax_gw3_corrections_2627.csv"
    (repo / path).parent.mkdir(parents=True)
    (repo / path).write_text("player,correction\nExample,1\n")
    assert publish(repo, dry_run=True).files == (path,)


@pytest.mark.parametrize("attack", ["source", "secret"])
def test_staging_is_revalidated(repo, monkeypatch, attack):
    change(repo)
    original = pub.subprocess.run
    def intercepted(cmd, **kwargs):
        result = original(cmd, **kwargs)
        if cmd[1] == "add":
            target = "app.py" if attack == "source" else DATA
            (repo / target).write_text("# unrelated\n" if attack == "source" else '{"password":"leaked"}')
            original([GIT, "add", "--", target], cwd=repo, capture_output=True, check=True)
        return result
    monkeypatch.setattr(pub.subprocess, "run", intercepted)
    head = git(repo, "rev-parse", "HEAD")
    result = publish(repo)
    assert result.status == "BLOCKED"
    assert git(repo, "rev-parse", "HEAD") == head


def test_remote_moves_between_plan_and_commit(repo, monkeypatch):
    change(repo)
    original = pub.subprocess.run
    fetches = []
    def intercepted(cmd, **kwargs):
        result = original(cmd, **kwargs)
        if cmd[1] == "fetch":
            fetches.append(True)
            if len(fetches) == 2:
                # A different valid object stands in for a concurrently fetched remote HEAD.
                tree = git(repo, "rev-parse", "HEAD^{tree}")
                other = git(repo, "commit-tree", tree, "-p", "HEAD", "-m", "remote moved")
                git(repo, "update-ref", "refs/remotes/origin/main", other)
        return result
    monkeypatch.setattr(pub.subprocess, "run", intercepted)
    head = git(repo, "rev-parse", "HEAD")
    result = publish(repo)
    assert result.status == "BLOCKED"
    assert any("Remote main moved during" in b for b in result.blockers)
    assert git(repo, "rev-parse", "HEAD") == head


def test_parquet_secret_content_is_scanned():
    import io
    import pyarrow as pa
    import pyarrow.parquet as pq
    buffer = io.BytesIO()
    pq.write_table(pa.table({"access_token": ["private-value"]}), buffer, compression="snappy")
    assert pub.has_secret("example.parquet", buffer.getvalue())


def test_manifest_is_explicit_and_excludes_historical_dumps():
    manifest = json.loads(pub.MANIFEST.read_text())
    assert DATA in manifest["paths"]
    assert all(pub.allowed(p, set(manifest["paths"])) for p in manifest["paths"])
    assert not pub.allowed("data/models/season_2526/advanced/player_event_data_2526.csv", set(manifest["paths"]))
    assert all("*" not in p for p in manifest["paths"])


def test_finalized_previous_gw_not_rewritten(monkeypatch):
    from types import SimpleNamespace
    from scripts import refresh_desktop_sources as desktop
    calls = []
    plan = SimpleNamespace(current_gw=3, previous_gw=2, previous_gw_status="FINALIZED",
                           whoscored=SimpleNamespace(status="CACHE_HIT"),
                           understat=SimpleNamespace(status="CACHE_HIT"))
    monkeypatch.setattr(desktop, "require_commissioner_writer", lambda name: None)
    monkeypatch.setattr(desktop, "build_smart_refresh_plan", lambda season: plan)
    monkeypatch.setattr(desktop, "_run", lambda script, *args: calls.append((script, args)) or 0)
    monkeypatch.setattr(desktop, "atomic_json", lambda *args: None)
    monkeypatch.setattr(desktop, "publish_refresh", lambda *args, **kwargs: pub.PublishResult("NO_ACTION_REQUIRED"))
    monkeypatch.setattr("sys.argv", ["refresh_desktop_sources.py"])
    monkeypatch.setattr(desktop, "desktop_dependencies", lambda: [])
    monkeypatch.setattr(desktop, "provider_statuses", lambda report: {"Fantrax":"PASS","WhoScored":"PASS","Understat":"PASS"})
    assert desktop.main() == 0
    assert not any(script == "build_current_data_integrity.py" for script, _ in calls)
    assert not any("--finalize" in args for _, args in calls)


def test_cli_dry_run_never_acquires_or_writes(monkeypatch):
    from types import SimpleNamespace
    from scripts import refresh_desktop_sources as desktop
    state = SimpleNamespace(status="CACHE_HIT")
    plan = SimpleNamespace(current_gw=3, correction_check_required=False, previous_gw_status="FINALIZED",
                           fantrax=state, whoscored=state, understat=state)
    monkeypatch.setattr(desktop, "require_commissioner_writer", lambda name: None)
    monkeypatch.setattr(desktop, "build_smart_refresh_plan", lambda season: plan)
    monkeypatch.setattr(desktop, "_run", lambda *args: pytest.fail("live acquisition"))
    monkeypatch.setattr(desktop, "atomic_json", lambda *args: pytest.fail("write"))
    def dry(*args, **kwargs):
        assert kwargs["dry_run"] and kwargs["refresh_status"] == "NOT_RUN"
        return pub.PublishResult("DRY_RUN")
    monkeypatch.setattr(desktop, "publish_refresh", dry)
    monkeypatch.setattr("sys.argv", ["refresh_desktop_sources.py", "--publish-dry-run"])
    monkeypatch.setattr(desktop, "desktop_dependencies", lambda: [])
    monkeypatch.setattr(desktop, "provider_statuses", lambda report: {"Fantrax":"PASS","WhoScored":"PASS","Understat":"PASS"})
    assert desktop.main() == 0
