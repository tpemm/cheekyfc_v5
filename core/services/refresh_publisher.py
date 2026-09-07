"""Fail-closed publishing of explicitly reviewed deployment products only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
import json
import io
import os
import re
import shutil
import subprocess

from core.services.machine_role import _local_config, require_commissioner_writer
from core.services.smart_refresh import status_succeeded
from fantrax.migration.package import sensitive

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/refresh_publish_manifest.json"
SECRET = re.compile(rb"""-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]+|Bearer\s+[A-Za-z0-9._-]{12,}|["']?(?:access_token|refresh_token|password|cookie|cookies|localStorage|sessionStorage|api_key|client_secret)["']?\s*[:=]""", re.I)


@dataclass(frozen=True)
class PublishResult:
    status: str
    files: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    commit: str | None = None


def allowed(path: str, paths: set[str]) -> bool:
    rel = PurePosixPath(path)
    return (path in paths and not rel.is_absolute() and '..' not in rel.parts
            and not sensitive(rel) and not any(word in path.lower() for word in
            ('data/raw/', 'auth', 'local_machine', '.env', '.venv', 'diagnostic',
             'migration', 'quarantine', 'screenshot', 'data/snapshots/'))
            and rel.suffix in {'.csv', '.json', '.parquet'})


def has_secret(path: str, content: bytes) -> bool:
    if path.endswith('.parquet'):
        import pyarrow.parquet as pq
        content = json.dumps(pq.read_table(io.BytesIO(content)).to_pylist(), default=str).encode()
    return bool(SECRET.search(content))


def publish_refresh(root: Path = ROOT, *, season: str = '2627', current_gw: int | None,
                    refresh_status: str, dry_run: bool = False,
                    env: dict[str, str] | None = None) -> PublishResult:
    """Dry-run fetches and inspects only; it never acquires, stages or publishes.

    Existing staged changes and local-only commits require manual review.
    Failures retain files and index, including our staging if a later gate fails.
    """
    files: tuple[str, ...] = ()
    commit = None
    blockers: list[str] = []
    git = shutil.which('git') or r'C:\Program Files\Git\cmd\git.exe'

    def run(*args: str) -> str:
        proc = subprocess.run([git, *args], cwd=root, capture_output=True, check=False)
        if proc.returncode:
            # stderr can include credential-bearing remote URLs.
            raise ValueError(f"Git {args[0]} failed (exit {proc.returncode}); inspect Git locally.")
        return proc.stdout.decode('utf-8', errors='strict').strip('\r\n')

    def names(*args: str) -> set[str]:
        return set(filter(None, run(*args).split('\0')))

    try:
        values = {**_local_config(), **os.environ} if env is None else env
        require_commissioner_writer('runtime data publishing', values)
        if values.get('COMMISSIONER_REFRESH_ENABLED', '').lower() != 'true':
            raise ValueError('Publishing requires explicit COMMISSIONER_REFRESH_ENABLED=true.')
        manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
        if season != manifest['season']:
            raise ValueError('Season has no reviewed publish manifest.')
        paths = set(manifest['paths'])
        for gw in (current_gw, (current_gw - 1) if current_gw and current_gw > 1 else None):
            if gw:
                paths.update(p.format(gw=gw) for p in manifest.get('gameweek_templates', []))
        if run('rev-parse', '--show-toplevel').replace('\\', '/').lower() != root.resolve().as_posix().lower():
            raise ValueError('Publishing requires the repository root.')
        if run('branch', '--show-current') != 'main':
            raise ValueError('Publishing requires branch main.')
        head = run('rev-parse', 'HEAD')
        dirty = names('diff', '--no-renames', '--name-only', '-z', 'HEAD', '--')
        untracked = names('ls-files', '--others', '--exclude-standard', '-z')
        files = tuple(sorted(p for p in dirty | untracked if allowed(p, paths)))
        blockers = [f'Unrelated dirty path: {p}' for p in sorted(dirty) if not allowed(p, paths)]
        blockers += [f'Uncommitted source path: {p}' for p in sorted(untracked) if not p.startswith('data/')]
        if names('diff', '--cached', '--no-renames', '--name-only', '-z'):
            blockers.append('Existing staged changes require manual review before publishing.')
        if not dry_run and not status_succeeded(refresh_status):
            blockers.append(f'Refresh quality gate: {refresh_status}')
        if not current_gw:
            blockers.append('Current GW is unknown.')
        # Fetch even for dry-run: remote eligibility needs fresh evidence.
        run('fetch', 'origin', 'refs/heads/main:refs/remotes/origin/main')
        ahead, behind = map(int, run('rev-list', '--left-right', '--count', 'HEAD...origin/main').split())
        if behind:
            blockers.append('Remote main moved: local HEAD is behind or diverged; reconcile manually.')
        if ahead:
            blockers.append('Local unpushed commits require manual review; publishing would also push them.')
        if blockers:
            return PublishResult('BLOCKED', files, tuple(blockers))
        if not files:
            return PublishResult('NO_ACTION_REQUIRED')
        for path in files:
            local = root / path
            if local.is_symlink() or not local.resolve().is_relative_to(root.resolve()):
                raise ValueError(f'Unsafe file: {path}')
            if local.exists() and has_secret(path, local.read_bytes()):
                raise ValueError(f'Possible secret/auth content: {path}')
        if dry_run:
            return PublishResult('DRY_RUN', files)
        run('add', '--', *files)
        staged = names('diff', '--cached', '--no-renames', '--name-only', '-z')
        if staged != set(files) or any(not allowed(p, paths) for p in staged):
            raise ValueError('Staged paths differ from the approved publish plan.')
        for path in staged:
            entry = run('ls-files', '--stage', '--', path)
            if entry and not entry.startswith(('100644 ', '100755 ')):
                raise ValueError(f'Unsafe staged file mode: {path}')
            if entry:
                proc = subprocess.run([git, 'show', ':' + path], cwd=root, capture_output=True, check=False)
                if proc.returncode or has_secret(path, proc.stdout):
                    raise ValueError(f'Unreadable or possible staged secret/auth content: {path}')
        if run('rev-parse', 'HEAD') != head or names('diff', '--name-only', '-z'):
            raise ValueError('Working tree or HEAD changed during publishing; review manually.')
        run('fetch', 'origin', 'refs/heads/main:refs/remotes/origin/main')
        if run('rev-parse', 'origin/main') != head:
            raise ValueError('Remote main moved during publishing; stopped.')
        run('commit', '-m', f'Data refresh: GW{current_gw} {datetime.now().date().isoformat()}')
        commit = run('rev-parse', 'HEAD')
        if run('rev-parse', 'HEAD^') != head or names('diff', '--no-renames', '--name-only', '-z', head, commit) != set(files):
            raise ValueError('Committed paths or parent differ from plan; push stopped.')
        for path in files:
            entry = run('ls-tree', commit, '--', path)
            if entry:
                if not entry.startswith(('100644 ', '100755 ')):
                    raise ValueError(f'Unsafe committed file mode: {path}')
                proc = subprocess.run([git, 'show', f'{commit}:{path}'], cwd=root, capture_output=True, check=False)
                if proc.returncode or has_secret(path, proc.stdout):
                    raise ValueError(f'Unreadable or possible committed secret/auth content: {path}')
        run('push', 'origin', f'{commit}:refs/heads/main')
        remote = run('ls-remote', 'origin', 'refs/heads/main').split()
        if not remote or remote[0] != commit:
            raise ValueError('Remote verification failed; inspect origin/main manually.')
        return PublishResult('PUBLISHED', files, commit=commit)
    except (OSError, ValueError, PermissionError, subprocess.SubprocessError) as exc:
        return PublishResult('BLOCKED', files, tuple(blockers + [str(exc)]), commit)
