from __future__ import annotations

import sys

import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, Set

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError


# -------------------------
# CONFIG
# -------------------------

LEAGUE_ID = "rg1i70pfmdhjhvn3"

URL_TEMPLATE_TEAM = (
    "https://www.fantrax.com/fantasy/league/{league_id}/team/roster;"
    "teamId={team_id};"
    "scoringCategoryType=5;"
    "period={gw};"
    "statsType=1;"
    "view=STATS;"
    "seasonOrProjection=SEASON_925_BY_PERIOD;"
    "timeframeTypeCode=BY_PERIOD"
)

OUT_DIR = PROJECT_ROOT / "data" / "raw" / "fantrax" / "team_rosters_weekly"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FILENAME_TEMPLATE = "fantrax_weeklystats_{manager}_GW{gw:02d}{ext}"

# Defaults (can be overridden by refresh tool via env vars)
START_GW = 1
END_GW = 28

DEFAULT_EXT = ".csv"

AUTH_STATE_PATH = PROJECT_ROOT / "data" / "raw" / "fantrax" / "fantrax_auth_state.json"
SHOW_BROWSER = True
GOTO_TIMEOUT_MS = 60_000

CLICK_PHASE_LIMIT_SEC = 12
DOWNLOAD_EVENT_TIMEOUT_MS = 30_000

DOWNLOAD_TOOLTIP_TEXT = "Download all as CSV"


# -------------------------
# Env-driven controls (set by refresh_weekplayer_rawdata.py)
# -------------------------
def _parse_int(s: str) -> Optional[int]:
    try:
        return int(str(s).strip())
    except Exception:
        return None


def _parse_only_gws(s: str) -> Set[int]:
    s = (s or "").strip()
    if not s:
        return set()
    out: Set[int] = set()
    for part in re.split(r"[,\s]+", s):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            ia, ib = _parse_int(a), _parse_int(b)
            if ia is None or ib is None:
                continue
            lo, hi = min(ia, ib), max(ia, ib)
            out.update(range(lo, hi + 1))
        else:
            i = _parse_int(part)
            if i is not None:
                out.add(i)
    return out


ONLY_GWS = _parse_only_gws(os.getenv("FANTRAX_ONLY_GWS", ""))
ENV_START = _parse_int(os.getenv("FANTRAX_START_GW", ""))
ENV_END = _parse_int(os.getenv("FANTRAX_END_GW", ""))

FORCE_OVERWRITE = os.getenv("FANTRAX_FORCE_OVERWRITE", "").strip().lower() in {"1", "true", "yes", "y"}

if ENV_START is not None:
    START_GW = ENV_START
if ENV_END is not None:
    END_GW = ENV_END


# -------------------------
# TEAMS
# -------------------------

@dataclass(frozen=True)
class TeamConfig:
    manager: str
    team_id: str


TEAMS: list[TeamConfig] = [
    TeamConfig("grant", "ss2dromsme3cbmga"),
    TeamConfig("garrett", "zxivny5tme3hojrx"),
    TeamConfig("evan", "eaz9h4hfme2wdh8p"),
    TeamConfig("liam", "qocqs3wjme34472y"),
    TeamConfig("nick", "ih2b4z8ome1job2n"),
    TeamConfig("paurav", "ne94j2bxme0vsmkq"),
    TeamConfig("rob", "zf53q9hdme32qmoe"),
    TeamConfig("tommy", "0t8m7z91mdhjhvye"),
    TeamConfig("jon", "fm7cv4p0me3j48nk"),
    TeamConfig("marco", "116s0o6ume0s7s58"),
    TeamConfig("will", "avv7b4d5me2tlsrt"),
    TeamConfig("yudesh", "xnt9wpm9me0us0r4"),
]


# -------------------------
# Helpers
# -------------------------

def slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s


def team_url(team_id: str, gw: int) -> str:
    return URL_TEMPLATE_TEAM.format(league_id=LEAGUE_ID, team_id=team_id, gw=gw)


def safe_ext_from_suggested(suggested: str) -> str:
    p = Path(suggested)
    return p.suffix.lower() if p.suffix else DEFAULT_EXT


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_is_effectively_empty_csv(path: Path) -> bool:
    try:
        data = path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return False
    if len(data) < 50:
        return True
    lines = [ln for ln in data.splitlines() if ln.strip()]
    return len(lines) <= 1


def goto_stable(page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    page.wait_for_timeout(1200)


def debug_snapshot(page, name: str) -> None:
    snap = OUT_DIR / name
    try:
        page.screenshot(path=str(snap), full_page=True)
        print(f"Saved screenshot: {snap}")
    except Exception as e:
        print(f"(screenshot failed: {e})")


def dismiss_notifications_popup(page) -> None:
    try:
        never_btn = page.get_by_role("button", name=re.compile(r"\bNever\b", re.I)).first
        if never_btn.is_visible(timeout=400):
            never_btn.click()
            page.wait_for_timeout(250)
    except Exception:
        pass


def archive_if_exists(path: Path) -> None:
    if not path.exists():
        return
    archive_dir = path.parent / "_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived = archive_dir / f"{path.stem}__archived_{ts}{path.suffix}"
    try:
        path.replace(archived)
        print(f"  archived existing -> {archived.name}")
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def click_export_icon_by_tooltip(page, tooltip_text: str = DOWNLOAD_TOOLTIP_TEXT) -> None:
    dismiss_notifications_popup(page)

    page.get_by_text("Game Week", exact=False).first.wait_for(timeout=15_000)

    tip = page.locator("div[role='tooltip']", has_text=tooltip_text).first
    tip.wait_for(state="attached", timeout=10_000)

    tip_id = tip.get_attribute("id")
    if not tip_id:
        raise RuntimeError("Tooltip found but no id attribute.")

    trigger = page.locator(f'[aria-describedby="{tip_id}"]').first
    trigger.wait_for(state="visible", timeout=10_000)

    try:
        trigger.click(timeout=5_000)
    except Exception:
        trigger.click(timeout=5_000, force=True)

    page.wait_for_timeout(150)


def download_team_week(page, manager: str, team_id: str, gw: int) -> Optional[Path]:
    url = team_url(team_id, gw)
    goto_stable(page, url)

    if page.get_by_text("Login", exact=True).count() > 0:
        raise RuntimeError("Looks logged out (Login visible). Recreate auth_state if needed.")

    click_start = time.time()
    last_beat = 0.0

    while True:
        if time.time() - last_beat > 2:
            print("...clicking export...")
            last_beat = time.time()

        try:
            with page.expect_download(timeout=DOWNLOAD_EVENT_TIMEOUT_MS) as dl_info:
                click_export_icon_by_tooltip(page, DOWNLOAD_TOOLTIP_TEXT)
            download = dl_info.value
            break
        except PWTimeoutError:
            if time.time() - click_start > CLICK_PHASE_LIMIT_SEC:
                return None
            time.sleep(0.7)
        except Exception as e:
            if time.time() - click_start > CLICK_PHASE_LIMIT_SEC:
                raise RuntimeError(f"Click phase failed: {e}")
            time.sleep(0.7)

    suggested = download.suggested_filename or f"fantrax_team_week_{manager}_gw{gw:02d}{DEFAULT_EXT}"
    ext = safe_ext_from_suggested(suggested)

    out_path = OUT_DIR / FILENAME_TEMPLATE.format(manager=slug(manager), gw=gw, ext=ext)

    if FORCE_OVERWRITE:
        archive_if_exists(out_path)

    download.save_as(out_path.as_posix())
    return out_path


def main() -> None:
    print(f"Today: {date.today().isoformat()}")
    print(f"Saving to: {OUT_DIR.resolve()}")
    print(f"Auth state: {AUTH_STATE_PATH}")
    print(f"Teams: {len(TEAMS)}")

    if ONLY_GWS:
        week_list = sorted([w for w in ONLY_GWS if w >= 1])
        print(f"Week selection: ONLY_GWS={week_list}")
    else:
        week_list = list(range(START_GW, END_GW + 1))
        print(f"Week range: START_GW={START_GW} END_GW={END_GW}")

    if FORCE_OVERWRITE:
        print("Mode: FORCE_OVERWRITE=ON (archives old files before writing)")
    print("")

    last_hash_by_manager: Dict[str, Optional[str]] = {t.manager: None for t in TEAMS}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not SHOW_BROWSER)

        if AUTH_STATE_PATH.exists():
            context = browser.new_context(accept_downloads=True, storage_state=str(AUTH_STATE_PATH))
        else:
            context = browser.new_context(accept_downloads=True)

        page = context.new_page()

        downloaded = 0
        missing = 0

        for gw in week_list:
            print(f"\n=== GW{gw:02d} ===")

            stop_flags = 0

            for team in TEAMS:
                manager = team.manager
                team_id = team.team_id

                out_path = OUT_DIR / FILENAME_TEMPLATE.format(manager=slug(manager), gw=gw, ext=DEFAULT_EXT)

                if out_path.exists() and not FORCE_OVERWRITE:
                    print(f"{manager}: already exists -> skip")
                    try:
                        last_hash_by_manager[manager] = sha256_file(out_path)
                    except Exception:
                        pass
                    continue

                print(f"{manager}: downloading…")
                try:
                    path = download_team_week(page, manager, team_id, gw)
                except Exception as e:
                    print(f"{manager}: FAILED -> {e}")
                    debug_snapshot(page, f"DEBUG_FAIL_{slug(manager)}_GW{gw:02d}.png")
                    missing += 1
                    continue

                if path is None:
                    print(f"{manager}: TIMED OUT (no download event)")
                    debug_snapshot(page, f"DEBUG_TIMEOUT_{slug(manager)}_GW{gw:02d}.png")
                    missing += 1
                    continue

                try:
                    this_hash = sha256_file(path)
                except Exception:
                    this_hash = None

                if file_is_effectively_empty_csv(path):
                    print(f"{manager}: empty-ish CSV -> removing + marking stop")
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    stop_flags += 1
                    continue

                prev_hash = last_hash_by_manager.get(manager)
                if prev_hash and this_hash and this_hash == prev_hash and not FORCE_OVERWRITE:
                    print(f"{manager}: duplicate of previous GW -> removing + marking stop")
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    stop_flags += 1
                    continue

                last_hash_by_manager[manager] = this_hash
                print(f"{manager}: saved -> {path.name}")
                downloaded += 1

                time.sleep(0.8)

            if not ONLY_GWS and stop_flags >= len(TEAMS):
                print(f"\nAll teams indicate GW{gw:02d} is not available yet. Stopping.")
                break

        context.close()
        browser.close()

    print(f"\nDone. downloaded={downloaded}, missing={missing}")


if __name__ == "__main__":
    main()