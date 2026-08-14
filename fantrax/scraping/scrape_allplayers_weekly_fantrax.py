from __future__ import annotations

import sys

import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Set

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError


# -------------------------
# CONFIG
# -------------------------

LEAGUE_ID = "rg1i70pfmdhjhvn3"

URL_TEMPLATE = (
    "https://www.fantrax.com/fantasy/league/{league_id}/players;"
    "miscDisplayType=1;"
    "pageNumber=1;"
    "seasonOrProjection=SEASON_925_BY_PERIOD;"
    "timeframeTypeCode=BY_PERIOD;"
    "startDate=2025-08-15;"
    "endDate={end_date};"
    "transactionPeriod={gw};"
    "view=STATS;"
    "statusOrTeamFilter=ALL"
)

OUT_DIR = PROJECT_ROOT / "data" / "raw" / "fantrax" / "all_players_weekly"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FILENAME_TEMPLATE = "Fantrax_WeeklyStats_AvailablePlayers_GW{gw:02d}{ext}"

# Defaults (can be overridden by refresh tool via env vars)
START_GW = 1
END_GW = 28

DEFAULT_EXT = ".csv"

AUTH_STATE_PATH = PROJECT_ROOT / "data" / "raw" / "fantrax" / "fantrax_auth_state.json"

SHOW_BROWSER = True
LOGIN_WAIT_SECONDS = 240

GOTO_TIMEOUT_MS = 60_000

CLICK_PHASE_LIMIT_SEC = 12
DOWNLOAD_EVENT_TIMEOUT_MS = 30_000


# -------------------------
# Env-driven controls (set by refresh_weekplayer_rawdata.py)
# -------------------------
# FANTRAX_ONLY_GWS="27,28"  -> only those weeks
# FANTRAX_START_GW="1"
# FANTRAX_END_GW="27"
# FANTRAX_FORCE_OVERWRITE="1" -> overwrite even if file exists (archives old)
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
# Helpers
# -------------------------

def safe_ext_from_suggested(suggested: str) -> str:
    p = Path(suggested)
    return p.suffix.lower() if p.suffix else DEFAULT_EXT


def league_url(gw: int, end_date: str) -> str:
    return URL_TEMPLATE.format(league_id=LEAGUE_ID, gw=gw, end_date=end_date)


def goto_stable(page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    page.wait_for_timeout(1400)


def debug_snapshot(page, name: str) -> None:
    snap = OUT_DIR / name
    try:
        page.screenshot(path=str(snap), full_page=True)
        print(f"Saved screenshot: {snap}")
    except Exception as e:
        print(f"(screenshot failed: {e})")


def out_path_for_gw(gw: int) -> Path:
    return OUT_DIR / FILENAME_TEMPLATE.format(gw=gw, ext=DEFAULT_EXT)


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
        # fallback: try unlink (last resort)
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def already_downloaded(gw: int) -> bool:
    # ✅ FIX: use exact expected filename existence (regex \b was failing on underscores)
    return out_path_for_gw(gw).exists()


def ensure_session(context, page, end_date: str) -> None:
    if AUTH_STATE_PATH.exists():
        print(f"Using saved session: {AUTH_STATE_PATH}")
        return

    test_url = league_url(gw=1, end_date=end_date)

    print("\nNo saved session found.")
    print("Opening your league stats page.")
    print("Click Login in the left sidebar and sign in (including any 2FA).")
    print(f"Waiting up to {LOGIN_WAIT_SECONDS} seconds for login to complete...\n")

    goto_stable(page, test_url)

    login_link = page.get_by_text("Login", exact=True)

    start = time.time()
    last_msg = 0.0
    while time.time() - start < LOGIN_WAIT_SECONDS:
        if time.time() - last_msg > 5:
            print("…waiting for login to complete…")
            last_msg = time.time()

        try:
            if login_link.count() == 0:
                context.storage_state(path=str(AUTH_STATE_PATH))
                print(f"✅ Saved session to: {AUTH_STATE_PATH}\n")
                return
        except Exception:
            pass

        time.sleep(1.0)

    raise RuntimeError("Login not detected in time (Login link never disappeared).")


def dismiss_notifications_popup(page) -> None:
    # Optional popup: “Receive notifications for your leagues?”
    try:
        never_btn = page.get_by_role("button", name=re.compile(r"\bNever\b", re.I)).first
        if never_btn.is_visible(timeout=400):
            never_btn.click()
            page.wait_for_timeout(250)
    except Exception:
        pass


def click_download_icon_by_tooltip(page) -> None:
    """
    Fantrax uses an Angular/Material tooltip:
      <div role="tooltip" id="cdk-describedby-message-...">Download all as CSV</div>

    The clickable icon usually has aria-describedby="<that id>".
    """
    dismiss_notifications_popup(page)

    page.get_by_text("Period Only", exact=False).first.wait_for(timeout=15_000)

    tip = page.locator("div[role='tooltip']", has_text="Download all as CSV").first
    tip.wait_for(state="attached", timeout=8_000)

    tip_id = tip.get_attribute("id")
    if not tip_id:
        raise RuntimeError("Tooltip found but had no id attribute.")

    trigger = page.locator(f'[aria-describedby="{tip_id}"]').first
    trigger.wait_for(state="visible", timeout=8_000)

    try:
        trigger.click(timeout=5_000)
    except Exception:
        trigger.click(timeout=5_000, force=True)

    page.wait_for_timeout(150)


def download_week(page, gw: int, end_date: str) -> Optional[Path]:
    url = league_url(gw, end_date)
    goto_stable(page, url)

    if page.get_by_text("Login", exact=True).count() > 0:
        raise RuntimeError("Looks logged out on this page (Login visible).")

    click_start = time.time()
    last_beat = 0.0

    while True:
        if time.time() - last_beat > 2:
            print("...trying to click download...")
            last_beat = time.time()

        try:
            with page.expect_download(timeout=DOWNLOAD_EVENT_TIMEOUT_MS) as dl_info:
                click_download_icon_by_tooltip(page)
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

    suggested = download.suggested_filename or f"fantrax_weekly_stats_gw{gw:02d}{DEFAULT_EXT}"
    ext = safe_ext_from_suggested(suggested)

    out_path = OUT_DIR / FILENAME_TEMPLATE.format(gw=gw, ext=ext)

    # overwrite behavior: archive old first
    if FORCE_OVERWRITE:
        archive_if_exists(out_path)

    download.save_as(out_path.as_posix())
    return out_path


def main() -> None:
    today = date.today().isoformat()
    print(f"Using endDate={today}")
    print(f"Saving to: {OUT_DIR.resolve()}")
    print(f"Session file: {AUTH_STATE_PATH}\n")

    if ONLY_GWS:
        week_list = sorted([w for w in ONLY_GWS if w >= 1])
        print(f"Week selection: ONLY_GWS={week_list}")
    else:
        week_list = list(range(START_GW, END_GW + 1))
        print(f"Week range: START_GW={START_GW} END_GW={END_GW}")
    if FORCE_OVERWRITE:
        print("Mode: FORCE_OVERWRITE=ON (archives old files before writing)")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not SHOW_BROWSER)

        if AUTH_STATE_PATH.exists():
            context = browser.new_context(accept_downloads=True, storage_state=str(AUTH_STATE_PATH))
        else:
            context = browser.new_context(accept_downloads=True)

        page = context.new_page()
        ensure_session(context, page, today)

        downloaded = 0
        skipped = 0
        missing = 0

        for gw in week_list:
            # default behavior: skip existing unless force overwrite
            if not FORCE_OVERWRITE and already_downloaded(gw):
                print(f"GW{gw:02d}: already exists -> skip")
                skipped += 1
                continue

            print(f"GW{gw:02d}: downloading…")
            try:
                path = download_week(page, gw, today)
            except Exception as e:
                print(f"GW{gw:02d}: FAILED -> {e}")
                debug_snapshot(page, f"DEBUG_FAIL_GW{gw:02d}.png")
                missing += 1
                continue

            if path is None:
                print(f"GW{gw:02d}: TIMED OUT (no download event after clicking icon)")
                debug_snapshot(page, f"DEBUG_TIMEOUT_GW{gw:02d}.png")
                missing += 1
            else:
                print(f"GW{gw:02d}: saved -> {path.name}")
                downloaded += 1

            time.sleep(1.0)

        context.close()
        browser.close()

    print(f"\nDone. downloaded={downloaded}, skipped={skipped}, missing={missing}")


if __name__ == "__main__":
    main()