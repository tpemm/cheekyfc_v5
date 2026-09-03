#!/usr/bin/env python3
"""Create and validate commissioner-local Fantrax browser state without refreshing data."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fantrax.live.config import load_live_season_config
from fantrax.live.weekly_acquisition import all_player_url


AUTH_PATH = ROOT / "data" / "raw" / "fantrax" / "2627" / "fantrax_auth_state.json"


def _login_visible(page) -> bool:
    return any(item.is_visible() for item in page.get_by_text("Login", exact=True).all())


def _authenticated_league_page(page, league_id: str, league_name: str) -> bool:
    if f"/fantasy/league/{league_id}/" not in urlsplit(page.url).path:
        return False
    if _login_visible(page):
        return False
    body = page.locator("body").inner_text().casefold()
    protected_export = page.locator('button[mattooltip="Download all as CSV"]').count() > 0
    return protected_export and league_name.casefold() in body


def _wait_for_login(context, league_id: str, league_name: str, timeout_seconds: int):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for page in context.pages:
            try:
                if _authenticated_league_page(page, league_id, league_name):
                    return page
            except Exception:
                continue
        if not context.pages:
            return None
        context.pages[0].wait_for_timeout(500)
    return None


def _validate_saved_state(playwright, league_id: str, period: int) -> dict[str, bool]:
    observed = {"authenticated_read_ok": False}
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(AUTH_PATH))
    page = context.new_page()

    def observe(response) -> None:
        try:
            request = response.request.post_data_json or {}
            messages = request.get("msgs", []) if isinstance(request, dict) else []
            if (
                urlsplit(response.url).path == "/fxpa/req"
                and any(item.get("method") == "getLiveScoringStats" for item in messages)
                and response.status == 200
            ):
                observed["authenticated_read_ok"] = True
        except Exception:
            return

    page.on("response", observe)
    page.goto(
        f"https://www.fantrax.com/fantasy/league/{league_id}/livescoring;period={period}",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not observed["authenticated_read_ok"]:
        page.wait_for_timeout(500)
    page_ok = (
        f"/fantasy/league/{league_id}/" in urlsplit(page.url).path
        and not _login_visible(page)
    )
    result = {
        "AUTH_STATE_EXISTS": AUTH_PATH.is_file() and AUTH_PATH.stat().st_size > 0,
        "AUTH_STATE_LOADS": True,
        "AUTHENTICATED_PAGE_OK": page_ok,
        "AUTHENTICATED_READ_OK": observed["authenticated_read_ok"],
    }
    context.close()
    browser.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-minutes", type=int, default=30)
    parser.add_argument("--period", type=int, default=2)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.timeout_minutes < 1:
        parser.error("--timeout-minutes must be at least 1")

    config = load_live_season_config()
    league_id = config.require_league_id()
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        if not args.validate_only:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(all_player_url(league_id, args.period), wait_until="domcontentloaded", timeout=60_000)
            print(
                "Fantrax login window is open. Complete login and leave the browser on the league Players page. "
                "Close the window to cancel.",
                flush=True,
            )
            authenticated_page = _wait_for_login(
                context, league_id, config.league_name, args.timeout_minutes * 60
            )
            if authenticated_page is None:
                context.close()
                browser.close()
                print(json.dumps({"status": "CANCELLED_OR_TIMED_OUT"}, indent=2))
                return 2
            context.storage_state(path=str(AUTH_PATH))
            context.close()
            browser.close()

        if not AUTH_PATH.exists():
            print(json.dumps({"status": "AUTH_STATE_MISSING"}, indent=2))
            return 2
        try:
            result = _validate_saved_state(playwright, league_id, args.period)
        except Exception as exc:
            result = {
                "AUTH_STATE_EXISTS": AUTH_PATH.exists(),
                "AUTH_STATE_LOADS": False,
                "AUTHENTICATED_PAGE_OK": False,
                "AUTHENTICATED_READ_OK": False,
                "error_type": type(exc).__name__,
            }
        passed = all(result.get(key, False) for key in (
            "AUTH_STATE_EXISTS",
            "AUTH_STATE_LOADS",
            "AUTHENTICATED_PAGE_OK",
            "AUTHENTICATED_READ_OK",
        ))
        print(json.dumps({"status": "PASS" if passed else "FAIL", **result}, indent=2))
        return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
